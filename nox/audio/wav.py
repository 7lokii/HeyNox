"""Leitura e escrita de WAV.

Só 16 bits, mono ou estéreo (o estéreo é reduzido a mono na leitura). É o
formato que o Piper produz e o que o Whisper espera, e evita arrastar `scipy`
para o núcleo.
"""

from __future__ import annotations

import wave
from array import array
from pathlib import Path

from nox.audio.types import SAMPLE_WIDTH, Pcm
from nox.config import NoxError


class WavError(NoxError):
    """O ficheiro não é um WAV que o Nox saiba ler."""


def read_wav(path: Path | str) -> tuple[Pcm, int]:
    """Devolve o áudio como PCM mono de 16 bits e a taxa de amostragem."""
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise WavError(f"{path}: não é um WAV válido ({exc})") from exc
    except FileNotFoundError as exc:
        raise WavError(f"{path}: ficheiro não encontrado") from exc

    if width != SAMPLE_WIDTH:
        raise WavError(f"{path}: só suporto WAV de 16 bits (este tem {width * 8})")
    if channels == 1:
        return Pcm(raw), rate
    if channels != 2:
        raise WavError(f"{path}: só suporto mono ou estéreo (este tem {channels} canais)")

    stereo = array("h", raw)
    mono = array("h", bytes(len(stereo) // 2 * SAMPLE_WIDTH))
    for index in range(len(mono)):
        mono[index] = (stereo[index * 2] + stereo[index * 2 + 1]) // 2
    return Pcm(mono.tobytes()), rate


def write_wav(path: Path | str, audio: Pcm, sample_rate: int) -> Path:
    """Grava o áudio em mono 16 bits e devolve o caminho escrito."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(SAMPLE_WIDTH)
        handle.setframerate(sample_rate)
        handle.writeframes(audio)
    return target
