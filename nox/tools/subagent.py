"""Sub-agentes: delegar uma tarefa a um contexto limpo.

O sub-agente vê o mesmo modelo e as mesmas ferramentas (menos esta), mas começa
sem histórico e sem memória. Serve para tarefas longas ou para não poluir a
conversa principal com passos intermédios.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import TYPE_CHECKING, Any

from nox.config import NoxError
from nox.tools.base import ToolResult

if TYPE_CHECKING:  # evita o ciclo agent -> subagent -> agent
    from nox.brain.agent import Agent


class SpawnAgentTool:
    name = "spawn_agent"
    description = (
        "Entrega uma tarefa a um sub-agente com contexto limpo e devolve o "
        "resultado. Útil para trabalho longo ou para isolar passos intermédios."
    )
    schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Tarefa completa e autónoma"},
            "timeout_s": {"type": "integer", "description": "Limite em segundos (padrão 90)"},
        },
        "required": ["task"],
    }

    def __init__(self, factory: Callable[[], Agent], *, timeout_s: float = 90.0) -> None:
        self._factory = factory
        self._timeout_s = timeout_s

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        task = str(arguments.get("task") or "").strip()
        if not task:
            return ToolResult(False, "falta a tarefa")
        try:
            timeout = float(arguments.get("timeout_s") or self._timeout_s)
        except (TypeError, ValueError):
            timeout = self._timeout_s
        timeout = max(5.0, min(300.0, timeout))

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._execute, task)
        try:
            return ToolResult(True, future.result(timeout=timeout))
        except FutureTimeout:
            future.cancel()
            return ToolResult(False, f"o sub-agente passou de {timeout:.0f}s e foi abandonado")
        except NoxError as exc:
            return ToolResult(False, f"o sub-agente falhou: {exc}")
        except Exception as exc:  # noqa: BLE001 — um sub-agente não derruba o principal
            return ToolResult(False, f"o sub-agente falhou: {type(exc).__name__}: {exc}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, task: str) -> str:
        return self._factory().reply(task)
