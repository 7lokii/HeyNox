"""Formato de áudio do núcleo.

PCM 16 bits, mono, little-endian, à taxa definida na config. `bytes` em vez de
`numpy.ndarray` para o núcleo continuar sem dependências: os adaptadores reais
(sounddevice, ficheiros WAV) convertem à entrada e à saída.
"""

from __future__ import annotations

import math
from array import array
from typing import NewType

Pcm = NewType("Pcm", bytes)

SAMPLE_WIDTH = 2  # bytes por amostra (16 bits)
SILENCE = Pcm(b"")


def frame_count(pcm: Pcm) -> int:
    return len(pcm) // SAMPLE_WIDTH


def duration_ms(pcm: Pcm, sample_rate: int) -> int:
    if sample_rate <= 0:
        raise ValueError("sample_rate tem de ser positivo")
    return round(frame_count(pcm) * 1000 / sample_rate)


def silence(duration_ms: int, sample_rate: int) -> Pcm:
    frames = round(max(duration_ms, 0) * sample_rate / 1000)
    return Pcm(b"\x00" * frames * SAMPLE_WIDTH)


def rms(pcm: Pcm) -> float:
    """Energia média do bloco. Suficiente para um VAD simples e para testes."""
    samples = array("h", pcm[: frame_count(pcm) * SAMPLE_WIDTH])
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))
