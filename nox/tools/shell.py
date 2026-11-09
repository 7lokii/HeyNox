"""Execução de comandos, com lista de permitidos.

Sem `shell=True`: o comando é dividido com `shlex` e executado como processo
direto. Metacaracteres de shell são recusados antes, para não haver forma de
encadear um segundo comando dentro do primeiro.
"""

from __future__ import annotations

import subprocess
from typing import Any

from nox.safety.approvals import ApprovalBroker
from nox.safety.sandbox import Sandbox
from nox.tools.base import ToolResult

MAX_OUTPUT = 4000


class RunCommandTool:
    name = "run_command"
    description = (
        "Executa um comando na raiz do projeto e devolve a saída. Comandos da "
        "lista de permitidos correm logo; os outros pedem aprovação na "
        "interface. Comandos destrutivos são sempre recusados."
    )
    schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Comando completo a executar"},
        },
        "required": ["command"],
    }

    def __init__(
        self,
        sandbox: Sandbox,
        *,
        timeout: float = 60.0,
        approvals: ApprovalBroker | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._timeout = timeout
        self._approvals = approvals

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = " ".join(str(arguments.get("command", "")).split())
        argv = self._sandbox.parse_command(command)

        if not self._sandbox.is_allowed_command(command):
            if self._approvals is None:
                return ToolResult(
                    False,
                    f"'{command}' não está na lista de comandos permitidos "
                    "e não há interface para aprovar",
                )
            approved = self._approvals.request(
                "run_command",
                f"Executar: {command}",
                detail=f"Comando: {command}\nPasta: {self._sandbox.root}",
            )
            if not approved:
                return ToolResult(False, f"não aprovado: {command}")

        try:
            completed = subprocess.run(  # noqa: S603 — argv validado, sem shell
                argv,
                cwd=self._sandbox.root,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"'{command}' passou de {self._timeout:.0f}s e foi parado")
        except FileNotFoundError:
            return ToolResult(False, f"'{argv[0]}' não está instalado ou não está no PATH")
        except OSError as exc:
            return ToolResult(False, f"não consegui executar '{command}': {exc}")

        output = (completed.stdout or "").strip()
        error = (completed.stderr or "").strip()
        parts = [f"saída (código {completed.returncode}):"]
        if output:
            parts.append(output[:MAX_OUTPUT])
        if error:
            parts.append("erros:\n" + error[:MAX_OUTPUT])
        if not output and not error:
            parts.append("(sem saída)")
        return ToolResult(completed.returncode == 0, "\n".join(parts))


def build_shell_tools(
    sandbox: Sandbox,
    *,
    timeout: float = 60.0,
    approvals: ApprovalBroker | None = None,
) -> list[Any]:
    return [RunCommandTool(sandbox, timeout=timeout, approvals=approvals)]
