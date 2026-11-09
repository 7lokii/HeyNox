"""Ferramenta para o Nox gerir as próprias rotinas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nox.automation.routines import RoutineError, RoutineStore
from nox.tools.base import ToolResult


class RoutineTool:
    name = "routine"
    description = (
        "Rotinas que correm sozinhas. 'create' guarda um prompt com agenda "
        "(daily@09:00, every@2h, once@2026-11-10T09:00); 'list' mostra; "
        "'delete' remove por id ou trecho do prompt."
    )
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "list", "delete"]},
            "prompt": {"type": "string", "description": "O que fazer quando disparar"},
            "schedule": {"type": "string", "description": "daily@HH:MM, every@Nm/h, once@ISO"},
            "key": {"type": "string", "description": "Id ou trecho do prompt (delete)"},
        },
        "required": ["action"],
    }

    def __init__(self, store: RoutineStore) -> None:
        self._store = store

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        try:
            if action == "create":
                routine = self._store.add(
                    str(arguments.get("prompt") or ""),
                    str(arguments.get("schedule") or ""),
                )
                return ToolResult(
                    True, f"rotina {routine.id} criada: {routine.schedule} — {routine.prompt}"
                )
            if action == "list":
                return ToolResult(True, self._list())
            if action == "delete":
                removed = self._store.remove(str(arguments.get("key") or ""))
                if not removed:
                    return ToolResult(False, "não encontrei essa rotina")
                message = "rotina removida" if removed == 1 else f"{removed} removidas"
                return ToolResult(True, message)
        except RoutineError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(False, f"ação desconhecida: {action or '(vazia)'}")

    def _list(self) -> str:
        routines = self._store.load()
        if not routines:
            return "não há rotinas"
        lines = []
        for routine in routines:
            state = "ativa" if routine.enabled else "desligada"
            last = (
                datetime.fromtimestamp(routine.last_run).strftime("%Y-%m-%d %H:%M")
                if routine.last_run
                else "nunca"
            )
            lines.append(
                f"{routine.id} [{state}] {routine.schedule} (última: {last}, "
                f"{routine.runs}x) — {routine.prompt}"
            )
        return "\n".join(lines)


def build_routine_tools(store: RoutineStore) -> list[Any]:
    return [RoutineTool(store)]
