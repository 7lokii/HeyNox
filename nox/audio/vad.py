"""Deteção de atividade de voz e segmentação de enunciados.

`Segmenter` é a peça que transforma um fluxo contínuo de blocos em frases
fechadas. Tem pré-roll (para não cortar a primeira sílaba), limite de duração
(para não acumular áudio infinito) e descarte de ruídos curtos.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from nox.audio.types import Pcm, duration_ms, rms


class VoiceActivityDetector(Protocol):
    def is_speech(self, chunk: Pcm) -> bool: ...


class EnergyVad:
    """VAD por energia. Não substitui o Silero, mas corre em qualquer máquina."""

    def __init__(self, threshold: float = 350.0) -> None:
        self.threshold = threshold

    def is_speech(self, chunk: Pcm) -> bool:
        return rms(chunk) >= self.threshold


@dataclass
class Segmenter:
    vad: VoiceActivityDetector
    sample_rate: int = 16000
    silence_ms: int = 700
    min_speech_ms: int = 300
    max_utterance_ms: int = 15000
    pre_roll_ms: int = 300

    _buffer: list[Pcm] = field(default_factory=list, repr=False)
    _pre_roll: deque[Pcm] = field(default_factory=deque, repr=False)
    _speech_ms: int = field(default=0, repr=False)
    _silence_ms: int = field(default=0, repr=False)
    _active: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        # Quantos blocos guardar antes da fala começar. Assume blocos de ~30 ms.
        self._pre_roll = deque(maxlen=max(1, self.pre_roll_ms // 30))

    def feed(self, chunk: Pcm) -> Pcm | None:
        """Consome um bloco e devolve o enunciado completo, quando fechar."""
        if not chunk:
            return None
        length = duration_ms(chunk, self.sample_rate)

        if self.vad.is_speech(chunk):
            if not self._active:
                self._start()
            self._buffer.append(chunk)
            self._speech_ms += length
            self._silence_ms = 0
            if self._speech_ms >= self.max_utterance_ms:
                return self._finish()
            return None

        if not self._active:
            self._pre_roll.append(chunk)
            return None

        self._buffer.append(chunk)
        self._silence_ms += length
        if self._silence_ms >= self.silence_ms:
            return self._finish()
        return None

    def flush(self) -> Pcm | None:
        """Fecha o enunciado em curso (usado quando o utilizador manda parar)."""
        return self._finish() if self._active else None

    def reset(self) -> None:
        self._buffer.clear()
        self._pre_roll.clear()
        self._speech_ms = 0
        self._silence_ms = 0
        self._active = False

    def _start(self) -> None:
        self._active = True
        self._buffer = list(self._pre_roll)
        self._pre_roll.clear()
        self._speech_ms = 0
        self._silence_ms = 0

    def _finish(self) -> Pcm | None:
        audio = Pcm(b"".join(self._buffer)) if self._speech_ms >= self.min_speech_ms else None
        self.reset()
        return audio
