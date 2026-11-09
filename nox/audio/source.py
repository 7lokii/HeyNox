"""Fonte de áudio.

O contrato é um `read(n)` bloqueante, que tanto o microfone real como um
ficheiro WAV ou um gerador de testes conseguem cumprir.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from nox.audio.types import SAMPLE_WIDTH, Pcm, resample
from nox.audio.wav import read_wav


class AudioSource(Protocol):
    sample_rate: int

    def read(self, frames: int) -> Pcm:
        """Devolve o bloco seguinte; `b""` quando a fonte acabou."""
        ...

    def close(self) -> None: ...


class FakeSource:
    """Fonte determinística: entrega os blocos dados e depois termina."""

    def __init__(self, chunks: Iterable[Pcm], *, sample_rate: int = 16000) -> None:
        self._chunks = list(chunks)
        self._index = 0
        self.sample_rate = sample_rate

    def read(self, frames: int) -> Pcm:
        if self._index >= len(self._chunks):
            return Pcm(b"")
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    def close(self) -> None:
        self._index = len(self._chunks)


class WavSource:
    """Reproduz um WAV como se fosse microfone.

    É o que permite testar o pipeline inteiro — VAD, STT, agente, TTS — sem
    ninguém a falar para o computador.
    """

    def __init__(self, path: Path | str, *, sample_rate: int = 16000) -> None:
        audio, rate = read_wav(path)
        self.sample_rate = sample_rate
        self._audio = audio if rate == sample_rate else resample(audio, rate, sample_rate)
        self._offset = 0

    def read(self, frames: int) -> Pcm:
        start = self._offset * SAMPLE_WIDTH
        end = start + frames * SAMPLE_WIDTH
        chunk = self._audio[start:end]
        self._offset += len(chunk) // SAMPLE_WIDTH
        return Pcm(chunk)

    def close(self) -> None:
        self._offset = len(self._audio) // SAMPLE_WIDTH
