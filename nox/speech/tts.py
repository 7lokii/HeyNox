"""Síntese de texto para voz."""

from __future__ import annotations

from typing import Protocol

from nox.audio.types import Pcm


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> Pcm:
        """Devolve o áudio da frase, à taxa de amostragem do sintetizador."""
        ...

    @property
    def sample_rate(self) -> int: ...


class NullSynthesizer:
    """Modo texto: não produz áudio e não falha."""

    sample_rate = 16000

    def synthesize(self, text: str) -> Pcm:
        return Pcm(b"")
