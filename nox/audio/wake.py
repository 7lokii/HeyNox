"""Deteção da wake word.

O contrato é incremental: cada bloco de áudio entra, um booleano sai. É assim
que o openWakeWord funciona e é assim que o microfone vai entregar os dados.
"""

from __future__ import annotations

from typing import Protocol

from nox.audio.types import Pcm


class WakeWordDetector(Protocol):
    def process(self, chunk: Pcm) -> bool:
        """True quando a wake word terminou de ser dita neste bloco."""
        ...


class AlwaysAwake:
    """Modo texto e testes: não há wake word a validar."""

    def process(self, chunk: Pcm) -> bool:
        return True


class NeverWake:
    """Silencia a ativação por voz sem desligar o pipeline."""

    def process(self, chunk: Pcm) -> bool:
        return False
