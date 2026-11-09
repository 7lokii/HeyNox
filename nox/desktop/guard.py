"""Modo de emergência: um travão único para todo o controlo do PC."""

from __future__ import annotations

import threading

from nox.config import NoxError


class DesktopError(NoxError):
    """Ação de desktop recusada ou falhada."""


class EmergencyStop:
    def __init__(self) -> None:
        self._active = threading.Event()

    def trigger(self) -> None:
        self._active.set()

    def clear(self) -> None:
        self._active.clear()

    @property
    def active(self) -> bool:
        return self._active.is_set()

    def check(self) -> None:
        if self.active:
            raise DesktopError(
                "modo de emergência ativo; diz 'retoma o controlo' ou carrega em Retomar"
            )


# Um por processo: a UI, o agente e as ferramentas veem o mesmo travão.
EMERGENCY = EmergencyStop()
