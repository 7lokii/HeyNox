"""Transcrição de voz para texto."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from nox.audio.denoise import spectral_gate
from nox.audio.types import Pcm, resample, trim_silence
from nox.config import Config
from nox.models import ModelError
from nox.optional import require

WHISPER_RATE = 16000


class Transcriber(Protocol):
    def transcribe(self, audio: Pcm, sample_rate: int) -> str:
        """Devolve o texto dito, ou `""` se não se percebeu nada."""
        ...


class NullTranscriber:
    def transcribe(self, audio: Pcm, sample_rate: int) -> str:
        return ""


class ScriptedTranscriber:
    """Devolve frases pré-definidas. Serve para demonstrar o loop sem modelo."""

    def __init__(self, phrases: Iterable[str]) -> None:
        self._phrases = list(phrases)

    def transcribe(self, audio: Pcm, sample_rate: int) -> str:
        return self._phrases.pop(0) if self._phrases else ""


class FasterWhisperTranscriber:
    """faster-whisper local (CTranslate2). Não precisa de PyTorch."""

    def __init__(
        self,
        model: str = "small",
        *,
        device: str = "auto",
        compute_type: str = "int8",
        language: str = "pt",
        initial_prompt: str = "",
        beam_size: int = 3,
        trim_silence: bool = True,
        denoise: bool = True,
        denoise_strength: float = 1.5,
    ) -> None:
        require("faster_whisper")
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model, device=device, compute_type=compute_type)
        self._language = language or None
        self._prompt = initial_prompt.strip() or None
        self._beam_size = beam_size
        self._trim = trim_silence
        self._denoise = denoise
        self._denoise_strength = denoise_strength

    def transcribe(self, audio: Pcm, sample_rate: int) -> str:
        import numpy as np

        if self._denoise:
            audio = spectral_gate(audio, sample_rate, strength=self._denoise_strength)
        if self._trim:
            audio = trim_silence(audio, sample_rate)
        if not audio:
            return ""
        if sample_rate != WHISPER_RATE:
            audio = resample(audio, sample_rate, WHISPER_RATE)
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(
            samples,
            language=self._language,
            beam_size=self._beam_size,
            vad_filter=False,
            initial_prompt=self._prompt,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


def build_transcriber(config: Config) -> Transcriber:
    """Constrói o transcritor configurado. O modelo é descarregado na 1.ª vez."""
    settings = config.stt
    if settings.provider == "faster-whisper":
        prompt = settings.initial_prompt.strip() or (
            f"O assistente chama-se {config.nox.name}. {config.nox.wake_word.title()}."
        )
        return FasterWhisperTranscriber(
            settings.model,
            device=settings.device,
            compute_type=settings.compute_type,
            language=settings.language,
            initial_prompt=prompt,
            beam_size=settings.beam_size,
            trim_silence=settings.trim_silence,
            denoise=settings.denoise,
            denoise_strength=settings.denoise_strength,
        )
    raise ModelError(f"stt.provider '{settings.provider}' ainda não está implementado")
