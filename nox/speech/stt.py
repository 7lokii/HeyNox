"""Transcrição de voz para texto."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from nox.audio.types import Pcm


class Transcriber(Protocol):
    def transcribe(self, audio: Pcm, sample_rate: int) -> str:
        """Devolve o texto dito, ou `""` se não se percebeu nada."""
        ...


class NullTranscriber:
    def transcribe(self, audio: Pcm, sample_rate: int) -> str:
        return ""


class ScriptedTranscriber:
    """Devolve frases pré-definidas. Serve para demonstrar o loop sem modelo."""

    def __init__(self, phrases: Iterable[str]) -> None:
        self._phrases = list(phrases)

    def transcribe(self, audio: Pcm, sample_rate: int) -> str:
        return self._phrases.pop(0) if self._phrases else ""
