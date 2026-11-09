"""Execução de comandos, com lista de permitidos.

Sem `shell=True`: o comando é dividido com `shlex` e executado como processo
direto. Metacaracteres de shell são recusados antes, para não haver forma de
encadear um segundo comando dentro do primeiro.
"""

from __future__ import annotations

import subprocess
from typing import Any

from nox.safety.sandbox import Sandbox
from nox.tools.base import ToolResult

MAX_OUTPUT = 4000


class RunCommandTool:
    name = "run_command"
    description = (
        "Executa um comando permitido na raiz do projeto e devolve a saída. "
        "Só funciona com comandos da lista de permitidos (ex.: git status, "
        "git diff, pytest, python -m pytest, ruff)."
    )
    schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Comando completo a executar"},
        },
        "required": ["command"],
    }

    def __init__(self, sandbox: Sandbox, *, timeout: float = 60.0) -> None:
        self._sandbox = sandbox
        self._timeout = timeout

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = str(arguments.get("command", "")).strip()
        argv = self._sandbox.check_command(command)

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


def build_shell_tools(sandbox: Sandbox, *, timeout: float = 60.0) -> list[Any]:
    return [RunCommandTool(sandbox, timeout=timeout)]
