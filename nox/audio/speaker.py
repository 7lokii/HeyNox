"""Reprodução de áudio."""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event, Thread
from typing import Protocol

from nox.audio.levels import BANDS, play_frames
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
    """Saída por PortAudio. Emite o espectro do que está a tocar."""

    def __init__(self, on_frame: Callable[[list[float]], None] | None = None) -> None:
        self._end_at = 0.0
        self._on_frame = on_frame

    def _spectrum(self, audio: Pcm, sample_rate: int) -> tuple[Event, Thread | None]:
        stop = Event()
        if self._on_frame is None or not audio:
            return stop, None
        thread = play_frames(audio, sample_rate, self._on_frame, stop)
        return stop, thread

    def _finish(self, stop: Event, thread: Thread | None) -> None:
        stop.set()
        if thread is not None:
            thread.join(timeout=1)
        if self._on_frame is not None:
            self._on_frame([0.0] * BANDS)

    def play(self, audio: Pcm, sample_rate: int) -> None:
        import numpy as np
        import sounddevice as sd

        if not audio:
            return
        stop, thread = self._spectrum(audio, sample_rate)
        try:
            sd.play(np.frombuffer(audio, dtype=np.int16), samplerate=sample_rate, blocking=True)
        finally:
            self._finish(stop, thread)

    def start(self, audio: Pcm, sample_rate: int) -> None:
        import numpy as np
        import sounddevice as sd

        if not audio:
            return
        self._end_at = time.monotonic() + duration_ms(audio, sample_rate) / 1000
        self._stop, self._thread = self._spectrum(audio, sample_rate)
        sd.play(np.frombuffer(audio, dtype=np.int16), samplerate=sample_rate, blocking=False)

    def is_playing(self) -> bool:
        return time.monotonic() < self._end_at

    def stop(self) -> None:
        import sounddevice as sd

        self._end_at = 0.0
        sd.stop()
        stop = getattr(self, "_stop", None)
        thread = getattr(self, "_thread", None)
        if stop is not None:
            self._finish(stop, thread)
            self._stop = None
            self._thread = None
