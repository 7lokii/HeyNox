"""Ferramentas e registo.

Uma ferramenta é nome + descrição + esquema JSON + execução. O registo trata do
que não pode falhar: medir o tempo, registar na auditoria e transformar exceções
em resultados — um erro de ferramenta não pode derrubar a conversa.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from nox.config import NoxError
from nox.safety.audit import AuditEntry, AuditLog

MAX_RESULT_CHARS = 6000


@dataclass
class ToolResult:
    ok: bool
    content: str


class Tool(Protocol):
    name: str
    description: str
    schema: dict[str, Any]

    def run(self, arguments: dict[str, Any]) -> ToolResult: ...


class ToolRegistry:
    def __init__(self, tools: list[Tool], *, audit: AuditLog | None = None) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self._audit = audit or AuditLog()

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        """No formato que os dois dialetos entendem (Anthropic e OpenAI)."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.schema,
            }
            for tool in self._tools.values()
        ]

    def run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        started = time.monotonic()
        tool = self._tools.get(name)
        if tool is None:
            result = ToolResult(False, f"ferramenta desconhecida: {name}")
        else:
            try:
                result = tool.run(arguments)
            except NoxError as exc:
                result = ToolResult(False, f"não permitido: {exc}")
            except Exception as exc:  # uma ferramenta nunca derruba o agente
                result = ToolResult(False, f"falhou: {type(exc).__name__}: {exc}")

        if len(result.content) > MAX_RESULT_CHARS:
            result = ToolResult(result.ok, result.content[:MAX_RESULT_CHARS] + "\n… (truncado)")

        self._audit.record(
            AuditEntry(
                tool=name,
                arguments=arguments,
                ok=result.ok,
                duration_ms=round((time.monotonic() - started) * 1000),
                detail=result.content[:200],
            )
        )
        return result
