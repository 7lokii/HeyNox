"""Estado partilhado entre o motor do Nox e a interface.

Uma só instância por processo. O motor escreve, o servidor HTTP lê — daí o
cadeado: o loop de voz corre numa thread e a UI noutra.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any


def _source(output: list[float], microphone: list[float]) -> str:
    """Quem está a fazer barulho: o Nox, o utilizador, ou ninguém."""
    if any(value > 0.02 for value in output):
        return "nox"
    if any(value > 0.02 for value in microphone):
        return "user"
    return "none"


@dataclass
class Turn:
    role: str
    text: str
    at: float


class NoxState:
    """Histórico e estado visível. Thread-safe."""

    def __init__(self, *, limit: int = 200) -> None:
        self._lock = threading.Lock()
        self._turns: list[Turn] = []
        self._status = "parado"
        self._voice = False
        self._levels: list[float] = []
        self._input_levels: list[float] = []
        self._limit = limit

    def add_turn(self, role: str, text: str) -> None:
        if not text.strip():
            return
        with self._lock:
            self._turns.append(Turn(role=role, text=text, at=time.time()))
            del self._turns[: -self._limit]

    def set_levels(self, levels: list[float]) -> None:
        """Espectro da voz do Nox (saída)."""
        with self._lock:
            self._levels = levels

    def set_input_levels(self, levels: list[float]) -> None:
        """Espectro do microfone (quem fala)."""
        with self._lock:
            self._input_levels = levels

    def set_status(self, status: str) -> None:
        with self._lock:
            self._status = status

    def set_voice(self, running: bool) -> None:
        with self._lock:
            self._voice = running
            # "a arrancar" porque carregar os modelos leva segundos; sem isto a
            # interface dizia "parado" enquanto o microfone já estava a abrir.
            self._status = "a arrancar" if running else "parado"

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "voice": self._voice,
                "levels": self._levels,
                "input_levels": self._input_levels,
                "source": _source(self._levels, self._input_levels),
                "turns": [asdict(turn) for turn in self._turns],
            }
