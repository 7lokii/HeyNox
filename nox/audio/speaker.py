"""Reprodução de áudio."""

from __future__ import annotations

import time
from typing import Protocol

from nox.audio.types import Pcm, duration_ms


class Speaker(Protocol):
    def play(self, audio: Pcm, sample_rate: int) -> None:
        """Reproduz até ao fim, bloqueando."""
        ...

    def start(self, audio: Pcm, sample_rate: int) -> None:
        """Arranca a reprodução sem bloquear (para poder ouvir por cima)."""
        ...

    def is_playing(self) -> bool: ...

    def stop(self) -> None: ...


class NullSpeaker:
    """Modo sem saída de áudio: não faz nada e não falha."""

    def play(self, audio: Pcm, sample_rate: int) -> None:
        return None

    def start(self, audio: Pcm, sample_rate: int) -> None:
        return None

    def is_playing(self) -> bool:
        return False

    def stop(self) -> None:
        return None


class SoundDeviceSpeaker:
    """Saída por PortAudio."""

    def __init__(self) -> None:
        self._end_at = 0.0

    def play(self, audio: Pcm, sample_rate: int) -> None:
        import numpy as np
        import sounddevice as sd

        if not audio:
            return
        sd.play(np.frombuffer(audio, dtype=np.int16), samplerate=sample_rate, blocking=True)

    def start(self, audio: Pcm, sample_rate: int) -> None:
        import numpy as np
        import sounddevice as sd

        if not audio:
            return
        self._end_at = time.monotonic() + duration_ms(audio, sample_rate) / 1000
        sd.play(np.frombuffer(audio, dtype=np.int16), samplerate=sample_rate, blocking=False)

    def is_playing(self) -> bool:
        return time.monotonic() < self._end_at

    def stop(self) -> None:
        import sounddevice as sd

        self._end_at = 0.0
        sd.stop()
