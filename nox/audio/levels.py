"""Espectro de áudio para a interface.

A interface desenha barras radiais a partir daqui. O que se vê é o áudio que
está mesmo a sair do altifalante, não uma animação a fingir: os quadros são
calculados a partir do PCM e emitidos ao ritmo da reprodução.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event, Thread

from nox.audio.types import Pcm

BANDS = 48
FPS = 25
MIN_HZ = 60.0
MAX_HZ = 8000.0


def spectrum_frames(
    audio: Pcm,
    sample_rate: int,
    *,
    bands: int = BANDS,
    fps: int = FPS,
) -> list[list[float]]:
    """Energia por banda ao longo do tempo, normalizada para 0..1."""
    import numpy as np

    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
    window = max(256, sample_rate // fps)
    if len(samples) < window:
        return []

    hann = np.hanning(window).astype(np.float32)
    frequencies = np.fft.rfftfreq(window, 1 / sample_rate)
    upper = min(MAX_HZ, sample_rate / 2 - 1)
    edges = np.geomspace(MIN_HZ, upper, bands + 1)
    indices = np.searchsorted(frequencies, edges)

    frames: list[list[float]] = []
    for start in range(0, len(samples) - window + 1, window):
        chunk = samples[start : start + window] * hann
        magnitude = np.abs(np.fft.rfft(chunk))
        frame = []
        for index in range(bands):
            low, high = int(indices[index]), int(indices[index + 1])
            # As bandas graves são mais estreitas que a resolução da FFT:
            # sem isto ficavam a zero e o espectro começava com barras mortas.
            high = max(high, low + 1)
            frame.append(float(magnitude[low:high].mean()))
        frames.append(frame)

    peak = max((max(frame) for frame in frames), default=0.0)
    if peak <= 0:
        return [[0.0] * bands for _ in frames]
    # Raiz quadrada: o ouvido não é linear e as bandas agudas têm menos energia.
    return [[min(1.0, (value / peak) ** 0.5) for value in frame] for frame in frames]


def emit_frames(
    frames: list[list[float]],
    on_frame: Callable[[list[float]], None],
    stop: Event,
    *,
    fps: int = FPS,
) -> None:
    """Emite os quadros ao ritmo da reprodução, até acabar ou até pararem."""
    interval = 1.0 / fps
    deadline = time.monotonic()
    for frame in frames:
        if stop.is_set():
            return
        on_frame(frame)
        deadline += interval
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)


def play_frames(
    audio: Pcm,
    sample_rate: int,
    on_frame: Callable[[list[float]], None],
    stop: Event,
    *,
    bands: int = BANDS,
    fps: int = FPS,
) -> Thread:
    """Arranca a emissão numa thread e devolve-a."""

    def run() -> None:
        try:
            frames = spectrum_frames(audio, sample_rate, bands=bands, fps=fps)
            emit_frames(frames, on_frame, stop, fps=fps)
        finally:
            on_frame([0.0] * bands)

    thread = Thread(target=run, daemon=True)
    thread.start()
    return thread
