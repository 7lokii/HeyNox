"""Reprodução de áudio."""

from __future__ import annotations

from typing import Protocol

from nox.audio.types import Pcm


class Speaker(Protocol):
    def play(self, audio: Pcm, sample_rate: int) -> None: ...

    def stop(self) -> None: ...


class NullSpeaker:
    """Modo sem saída de áudio: não faz nada e não falha."""

    def play(self, audio: Pcm, sample_rate: int) -> None:
        return None

    def stop(self) -> None:
        return None


class SoundDeviceSpeaker:
    """Saída por PortAudio. `play` bloqueia até o áudio terminar."""

    def play(self, audio: Pcm, sample_rate: int) -> None:
        import numpy as np
        import sounddevice as sd

        if not audio:
            return
        sd.play(np.frombuffer(audio, dtype=np.int16), samplerate=sample_rate, blocking=True)

    def stop(self) -> None:
        import sounddevice as sd

        sd.stop()
