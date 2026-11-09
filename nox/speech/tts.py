"""Síntese de texto para voz."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from nox.audio.types import Pcm
from nox.config import Config
from nox.models import ModelError, ensure_piper_voice
from nox.optional import require

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE_END = re.compile(r"(?<=[,;:])\s+")


def split_sentences(text: str, *, max_chars: int = 120) -> list[str]:
    """Parte a resposta em pedaços faláveis.

    Frases curtas chegam mais depressa ao altifalante: sintetizar 20 caracteres
    demora uma fracção do que sintetizar 200. Frases muito longas são ainda
    cortadas nas vírgulas.
    """
    parts = [part.strip() for part in _SENTENCE_END.split(text.strip()) if part.strip()]
    chunks: list[str] = []
    for part in parts:
        if len(part) <= max_chars:
            chunks.append(part)
            continue
        for clause in _CLAUSE_END.split(part):
            chunks.extend(_wrap(clause.strip(), max_chars))
    return [chunk for chunk in chunks if chunk]


def _wrap(text: str, max_chars: int) -> list[str]:
    """Quebra por palavras quando nem uma oração cabe no limite."""
    if len(text) <= max_chars:
        return [text]
    lines: list[str] = []
    current = ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> Pcm:
        """Devolve o áudio da frase, à taxa de amostragem do sintetizador."""
        ...

    @property
    def sample_rate(self) -> int: ...


class NullSynthesizer:
    """Modo texto: não produz áudio e não falha."""

    sample_rate = 16000

    def synthesize(self, text: str) -> Pcm:
        return Pcm(b"")


class PiperSynthesizer:
    """Piper local (ONNX). Vozes pt-PT chamam-se `pt_PT-<nome>-<qualidade>`."""

    def __init__(self, model_path: Path | str, *, speed: float = 1.0) -> None:
        require("piper")
        from piper import PiperVoice, SynthesisConfig

        self._voice = PiperVoice.load(str(model_path))
        # No Piper, length_scale maior significa fala mais lenta.
        self._config = SynthesisConfig(length_scale=1.0 / speed if speed != 1.0 else None)
        self._sample_rate = int(self._voice.config.sample_rate)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def synthesize(self, text: str) -> Pcm:
        text = text.strip()
        if not text:
            return Pcm(b"")
        chunks = [chunk.audio_int16_bytes for chunk in self._voice.synthesize(text, self._config)]
        return Pcm(b"".join(chunks))


def build_synthesizer(
    config: Config, *, progress: Callable[[str], None] | None = None
) -> Synthesizer:
    """Constrói o sintetizador configurado, descarregando a voz se faltar."""
    settings = config.tts
    if settings.provider == "piper":
        model = ensure_piper_voice(settings.voice, progress=progress)
        return PiperSynthesizer(model, speed=settings.speed)
    if settings.provider == "edge":
        from nox.speech.edge import EdgeSynthesizer

        if "_" in settings.voice:
            raise ModelError(
                "tts.voice tem um nome de voz Piper; para o edge usa "
                "pt-PT-DuarteNeural ou pt-PT-RaquelNeural"
            )
        return EdgeSynthesizer(settings.voice, speed=settings.speed)
    raise ModelError(f"tts.provider '{settings.provider}' ainda não está implementado")
