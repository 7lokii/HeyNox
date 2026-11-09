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


def trim_silence(
    pcm: Pcm,
    sample_rate: int,
    *,
    threshold: float = 200.0,
    frame_ms: int = 30,
    pad_ms: int = 100,
) -> Pcm:
    """Corta o silêncio das pontas, deixando uma margem.

    O Segmenter já entrega pré-roll e cauda; o Whisper não precisa deles e cada
    segundo de silêncio é tempo de transcrição.
    """
    frame_bytes = round(sample_rate * frame_ms / 1000) * SAMPLE_WIDTH
    if frame_bytes <= 0 or len(pcm) <= frame_bytes * 2:
        return pcm

    frames = [
        Pcm(pcm[offset : offset + frame_bytes])
        for offset in range(0, len(pcm) - frame_bytes + 1, frame_bytes)
    ]
    voiced = [index for index, frame in enumerate(frames) if rms(frame) >= threshold]
    if not voiced:
        return Pcm(b"")

    margin = max(1, pad_ms // frame_ms)
    first = max(0, voiced[0] - margin) * frame_bytes
    last = min(len(frames), voiced[-1] + 1 + margin) * frame_bytes
    return Pcm(pcm[first:last])


def resample(pcm: Pcm, from_rate: int, to_rate: int) -> Pcm:
    """Reamostragem por interpolação linear.

    Chega para voz: o Whisper quer 16 kHz e o Piper produz 22,05 kHz. Não é
    anti-aliasing de livro, mas a diferença é inaudível para reconhecimento.
    """
    if from_rate == to_rate or from_rate <= 0 or to_rate <= 0:
        return pcm
    source = array("h", pcm)
    if not source:
        return Pcm(b"")

    ratio = to_rate / from_rate
    out_length = int(len(source) * ratio)
    output = array("h", bytes(out_length * SAMPLE_WIDTH))
    last = len(source) - 1
    for index in range(out_length):
        position = index / ratio
        left = int(position)
        right = min(left + 1, last)
        fraction = position - left
        output[index] = int(source[left] + (source[right] - source[left]) * fraction)
    return Pcm(output.tobytes())
