"""Ferramentas de ficheiros: ler, listar, escrever e editar.

Escrever exige aprovação: o pedido aparece na interface com o diff, e só depois
de um "sim" é que o ficheiro é tocado. Sem interface, a resposta é não.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from nox.safety.approvals import ApprovalBroker
from nox.safety.sandbox import Sandbox, SandboxError
from nox.tools.base import ToolResult

MAX_BYTES = 200_000


def _diff(before: str, after: str, name: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"{name} (antes)",
            tofile=f"{name} (depois)",
            lineterm="",
            n=3,
        )
    )


def _counts(diff: str) -> tuple[int, int]:
    added = sum(
        1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")
    )
    return added, removed


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


class WriteFileTool:
    name = "write_file"
    description = (
        "Cria ou substitui um ficheiro de texto do projeto. Pede aprovação na "
        "interface e mostra o diff. Para mudar só um trecho, prefere edit_file."
    )
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho do ficheiro"},
            "content": {"type": "string", "description": "Conteúdo completo a gravar"},
        },
        "required": ["path", "content"],
    }

    def __init__(
        self,
        sandbox: Sandbox,
        *,
        approvals: ApprovalBroker | None = None,
        confirm: bool = True,
    ) -> None:
        self._sandbox = sandbox
        self._approvals = approvals
        self._confirm = confirm

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        raw = str(arguments.get("path", "")).strip()
        content = arguments.get("content")
        if not raw:
            return ToolResult(False, "falta o caminho")
        if not isinstance(content, str):
            return ToolResult(False, "falta o conteúdo")

        path = self._sandbox.resolve(raw)
        before = ""
        if path.exists():
            if not path.is_file():
                return ToolResult(False, f"{raw} não é um ficheiro")
            if path.stat().st_size > MAX_BYTES:
                return ToolResult(False, f"{raw} é grande demais para substituir")
            try:
                before = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return ToolResult(False, f"{raw} não parece ser texto")
            except OSError as exc:
                return ToolResult(False, f"não consegui ler {raw}: {exc}")

        if before == content:
            return ToolResult(True, f"{raw} já tem esse conteúdo")

        diff = _diff(before, content, raw)
        added, removed = _counts(diff)
        lines = len(content.splitlines())
        summary = (
            f"Alterar {raw} (+{added} −{removed})"
            if before
            else f"Criar {raw} ({lines} {'linha' if lines == 1 else 'linhas'})"
        )
        if self._confirm and not self._approve(summary, diff):
            return ToolResult(False, f"não aprovado: escrever {raw}")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(False, f"não consegui escrever {raw}: {exc}")
        return ToolResult(True, f"escrito {raw} ({len(content.splitlines())} linhas)")

    def _approve(self, summary: str, diff: str) -> bool:
        if self._approvals is None:
            return False
        return self._approvals.request("write_file", summary, diff)


class EditFileTool:
    name = "edit_file"
    description = (
        "Substitui um trecho exato de um ficheiro por outro. O trecho antigo "
        "tem de aparecer uma só vez. Pede aprovação e mostra o diff."
    )
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho do ficheiro"},
            "old": {"type": "string", "description": "Texto exato a substituir"},
            "new": {"type": "string", "description": "Texto novo"},
        },
        "required": ["path", "old", "new"],
    }

    def __init__(
        self,
        sandbox: Sandbox,
        *,
        approvals: ApprovalBroker | None = None,
        confirm: bool = True,
    ) -> None:
        self._sandbox = sandbox
        self._approvals = approvals
        self._confirm = confirm

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        raw = str(arguments.get("path", "")).strip()
        old = arguments.get("old")
        new = arguments.get("new")
        if not raw:
            return ToolResult(False, "falta o caminho")
        if not isinstance(old, str) or not old:
            return ToolResult(False, "falta o texto a substituir")
        if not isinstance(new, str):
            return ToolResult(False, "falta o texto novo")

        path = self._sandbox.resolve(raw)
        if not path.is_file():
            return ToolResult(False, f"{raw} não é um ficheiro")
        try:
            before = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            return ToolResult(False, f"não consegui ler {raw}: {exc}")

        occurrences = before.count(old)
        if occurrences == 0:
            return ToolResult(False, f"não encontrei esse texto em {raw}")
        if occurrences > 1:
            return ToolResult(
                False, f"esse texto aparece {occurrences} vezes em {raw}; dá mais contexto"
            )

        after = before.replace(old, new, 1)
        diff = _diff(before, after, raw)
        added, removed = _counts(diff)
        summary = f"Editar {raw} (+{added} −{removed})"
        if self._confirm and not self._approve(summary, diff):
            return ToolResult(False, f"não aprovado: editar {raw}")

        try:
            path.write_text(after, encoding="utf-8")
        except OSError as exc:
            return ToolResult(False, f"não consegui escrever {raw}: {exc}")
        return ToolResult(True, f"editado {raw} (+{added} −{removed})")

    def _approve(self, summary: str, diff: str) -> bool:
        if self._approvals is None:
            return False
        return self._approvals.request("edit_file", summary, diff)


def build_file_tools(
    sandbox: Sandbox,
    *,
    approvals: ApprovalBroker | None = None,
    confirm_writes: bool = True,
) -> list[Any]:
    return [
        ReadFileTool(sandbox),
        ListDirTool(sandbox),
        WriteFileTool(sandbox, approvals=approvals, confirm=confirm_writes),
        EditFileTool(sandbox, approvals=approvals, confirm=confirm_writes),
    ]


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
