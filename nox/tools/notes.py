"""Notas rápidas num ficheiro Markdown.

Distinto da memória: a memória guarda factos sobre o utilizador e é injetada no
prompt; as notas são um bloco de apontamentos que o Nox escreve quando lhe pedem
("aponta que amanhã há reunião às 10"). Ficam em `data/notes.md`, dentro da
sandbox e legíveis pelo utilizador.

Escrever uma nota não pede aprovação: é o caderno do próprio Nox, não um
ficheiro do projeto. A chamada continua a ser auditada.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from nox.safety.sandbox import Sandbox
from nox.tools.base import ToolResult

NOTES_PATH = "data/notes.md"
MAX_NOTE = 2000
LIST_LIMIT = 20


class NotesTool:
    name = "notes"
    description = (
        "Apontamentos rápidos. Ação 'add' guarda uma nota com data e hora; "
        "ação 'list' mostra as últimas notas. Para factos sobre o utilizador, "
        "usa a memória em vez disto."
    )
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list"]},
            "text": {"type": "string", "description": "Texto da nota (só em 'add')"},
        },
        "required": ["action"],
    }

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def _path(self) -> Path:
        return self._sandbox.resolve(NOTES_PATH)

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        if action == "add":
            return self._add(str(arguments.get("text") or "").strip())
        if action == "list":
            return self._list()
        return ToolResult(False, f"ação desconhecida: {action or '(vazia)'}")

    def _add(self, text: str) -> ToolResult:
        if not text:
            return ToolResult(False, "falta o texto da nota")
        if len(text) > MAX_NOTE:
            return ToolResult(False, f"a nota é grande demais ({len(text)} caracteres)")
        path = self._path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            with path.open("a", encoding="utf-8") as handle:
                if path.stat().st_size == 0:
                    handle.write("# Notas do Nox\n\n")
                handle.write(f"- {stamp} — {text}\n")
        except OSError as exc:
            return ToolResult(False, f"não consegui guardar a nota: {exc}")
        return ToolResult(True, f"nota guardada: {text}")

    def _list(self) -> ToolResult:
        path = self._path()
        if not path.is_file():
            return ToolResult(True, "ainda não há notas")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return ToolResult(False, f"não consegui ler as notas: {exc}")
        notes = [line for line in lines if line.startswith("- ")]
        if not notes:
            return ToolResult(True, "ainda não há notas")
        return ToolResult(True, "\n".join(notes[-LIST_LIMIT:]))


def build_notes_tools(sandbox: Sandbox) -> list[Any]:
    return [NotesTool(sandbox)]
