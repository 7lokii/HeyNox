"""Fonte de áudio.

O contrato é um `read(n)` bloqueante, que tanto o microfone real como um
ficheiro WAV ou um gerador de testes conseguem cumprir.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from nox.audio.types import Pcm, silence


class AudioSource(Protocol):
    sample_rate: int

    def read(self, frames: int) -> Pcm:
        """Devolve o bloco seguinte; `b""` quando a fonte acabou."""
        ...

    def close(self) -> None: ...


class FakeSource:
    """Fonte determinística: entrega os blocos dados e depois silêncio."""

    def __init__(self, chunks: Iterable[Pcm], *, sample_rate: int = 16000) -> None:
        self._chunks = list(chunks)
        self._index = 0
        self.sample_rate = sample_rate

    def read(self, frames: int) -> Pcm:
        if self._index >= len(self._chunks):
            return silence(round(frames * 1000 / self.sample_rate), self.sample_rate)
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    def close(self) -> None:
        self._index = len(self._chunks)
