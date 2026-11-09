"""Ferramentas de ficheiros: ler e listar.

Só leitura nesta fase. Escrever fica para quando houver aprovação na interface —
alterar ficheiros sem confirmação é o género de coisa que não se estreia sem
rede de segurança.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nox.safety.sandbox import Sandbox, SandboxError
from nox.tools.base import ToolResult

MAX_BYTES = 200_000


class ReadFileTool:
    name = "read_file"
    description = (
        "Lê um ficheiro de texto do projeto. Usa caminhos relativos à raiz do "
        "projeto. Devolve o conteúdo, truncado se for muito grande."
    )
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho do ficheiro"},
            "max_lines": {"type": "integer", "description": "Máximo de linhas"},
        },
        "required": ["path"],
    }

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        raw = str(arguments.get("path", "")).strip()
        if not raw:
            return ToolResult(False, "falta o caminho")

        path = self._sandbox.resolve(raw)
        if not path.is_file():
            return ToolResult(False, f"{raw} não é um ficheiro")
        if path.stat().st_size > MAX_BYTES:
            return ToolResult(False, f"{raw} é grande demais para ler de uma vez")

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(False, f"{raw} não parece ser texto")
        except OSError as exc:
            return ToolResult(False, f"não consegui ler {raw}: {exc}")

        limit = int(arguments.get("max_lines") or 400)
        lines = text.splitlines()
        if len(lines) > limit:
            lines = [*lines[:limit], f"… ({len(lines) - limit} linhas a mais)"]
        return ToolResult(True, "\n".join(lines))


class ListDirTool:
    name = "list_dir"
    description = "Lista o conteúdo de uma pasta do projeto, com tamanhos."
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Pasta (por omissão a raiz)"}},
        "required": [],
    }

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        raw = str(arguments.get("path") or ".")
        try:
            path = self._sandbox.resolve(raw)
        except SandboxError as exc:
            return ToolResult(False, str(exc))
        if not path.is_dir():
            return ToolResult(False, f"{raw} não é uma pasta")

        lines = []
        for entry in sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name)):
            if entry.name in {"__pycache__", ".git", "node_modules"}:
                continue
            suffix = "/" if entry.is_dir() else f"  {entry.stat().st_size} B"
            lines.append(f"{entry.name}{suffix}")
        return ToolResult(True, "\n".join(lines) or "(vazio)")


def build_file_tools(sandbox: Sandbox) -> list[Any]:
    return [ReadFileTool(sandbox), ListDirTool(sandbox)]


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
