"""Pedidos de aprovação entre as ferramentas e a interface.

O modelo pede uma ação sensível (escrever um ficheiro, correr um comando fora da
lista). A ferramenta **bloqueia** e publica o pedido; a interface mostra-o e
devolve sim ou não. Sem ninguém para decidir, a resposta é não — o silêncio
nunca vale como aprovação.

Uma instância por processo, partilhada entre o agente e o servidor HTTP. O
`threading.Event` é o que permite à ferramenta esperar sem ocupar a CPU.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from nox.safety.audit import AuditEntry, AuditLog

MAX_DETAIL_CHARS = 4000


@dataclass
class Approval:
    id: str
    action: str
    summary: str
    detail: str
    created_at: float
    event: threading.Event = field(default_factory=threading.Event, repr=False)
    approved: bool = False
    decided: bool = False

    def public(self) -> dict[str, Any]:
        """O que a interface pode ver. O evento fica de fora."""
        return {
            "id": self.id,
            "action": self.action,
            "summary": self.summary,
            "detail": self.detail,
            "created_at": self.created_at,
        }


class ApprovalBroker:
    """Fila de pedidos à espera de decisão. Thread-safe."""

    def __init__(self, *, timeout: float = 45.0, full_access: bool = False) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, Approval] = {}
        self._timeout = timeout
        self._full_access = full_access
        self._audit = AuditLog()

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def full_access(self) -> bool:
        return self._full_access

    def set_full_access(self, value: bool) -> None:
        """Ligado ou desligado em execução, sem reiniciar a app."""
        self._full_access = bool(value)

    def request(self, action: str, summary: str, detail: str = "") -> bool:
        """Bloqueia até haver decisão. Devolve False no tempo esgotado.

        Com acesso total, devolve True de imediato. Mesmo assim fica registado:
        sem essa linha não haveria forma de saber o que foi feito sem perguntar.
        """
        if self._full_access:
            self._audit.record(
                AuditEntry(
                    tool=f"aprovação:auto:{action}",
                    arguments={"summary": summary, "detail": detail[:MAX_DETAIL_CHARS]},
                    ok=True,
                    duration_ms=0,
                    detail="acesso total",
                )
            )
            return True

        approval = Approval(
            id=uuid.uuid4().hex[:12],
            action=action,
            summary=summary,
            detail=detail[:MAX_DETAIL_CHARS],
            created_at=time.time(),
        )
        with self._lock:
            self._pending[approval.id] = approval
        try:
            decided = approval.event.wait(self._timeout)
            return bool(decided and approval.approved)
        finally:
            with self._lock:
                self._pending.pop(approval.id, None)

    def decide(self, approval_id: str, approved: bool) -> bool:
        """Chamado pela interface. False se o pedido já não existir."""
        with self._lock:
            approval = self._pending.get(approval_id)
        if approval is None:
            return False
        approval.approved = bool(approved)
        approval.decided = True
        approval.event.set()
        return True

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return [approval.public() for approval in self._pending.values()]

    def cancel_all(self) -> None:
        """Recusa tudo o que estiver à espera (fecho da interface)."""
        with self._lock:
            approvals = list(self._pending.values())
        for approval in approvals:
            approval.approved = False
            approval.decided = True
            approval.event.set()
