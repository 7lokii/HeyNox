"""Transcrição de voz para texto."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import uuid
import wave
from collections.abc import Iterable
from typing import Protocol

from nox.audio.denoise import spectral_gate
from nox.audio.types import Pcm, resample, trim_silence
from nox.config import Config
from nox.models import ModelError
from nox.optional import require

WHISPER_RATE = 16000


def looks_hallucinated(text: str, prompt: str) -> bool:
    """True quando o modelo devolveu o próprio prompt em vez de fala.

    O Whisper, em áudio sem fala clara, tende a repetir o `initial_prompt`.
    Sem este filtro, o Nox "ouve" a sua própria configuração e responde-lhe.
    """
    if not prompt.strip() or not text.strip():
        return not text.strip()

    def words(value: str) -> list[str]:
        clean = "".join(ch if ch.isalnum() else " " for ch in value.lower())
        return clean.split()

    heard = words(text)
    if not heard:
        return True
    reference = set(words(prompt))
    if not reference:
        return False
    overlap = len(set(heard) & reference) / len(set(heard))
    if overlap > 0.8:
        return True
    return _is_repetitive(heard)


def _is_repetitive(words: list[str]) -> bool:
    """Deteta saídas em loop: a mesma sequência repetida sem fim."""
    if len(words) < 6:
        return False
    trigrams = [" ".join(words[index : index + 3]) for index in range(len(words) - 2)]
    return len(set(trigrams)) < len(trigrams) * 0.5


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
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if looks_hallucinated(text, self._prompt or ""):
            return ""
        return text


class OpenAiTranscriber:
    """Transcrição por API compatível com OpenAI (`/audio/transcriptions`).

    Groq, OpenAI e afins. Muito mais rápido e preciso do que o modelo pequeno
    local — a troco de o áudio sair do PC. É a peça que o FreeFlow usa.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "whisper-large-v3-turbo",
        *,
        language: str = "pt",
        timeout: float = 30.0,
    ) -> None:
        self._url = base_url.rstrip("/") + "/audio/transcriptions"
        self._key = api_key
        self._model = model
        self._language = language
        self._timeout = timeout

    def transcribe(self, audio: Pcm, sample_rate: int) -> str:
        if not audio:
            return ""
        boundary = f"----nox{uuid.uuid4().hex}"
        payload = _multipart(boundary, self._model, self._language, audio, sample_rate)
        request = urllib.request.Request(  # noqa: S310
            self._url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise ModelError(f"a transcrição na cloud falhou ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelError(f"sem ligação ao serviço de transcrição: {exc}") from exc
        text = str(data.get("text", "")).strip()
        return "" if looks_hallucinated(text, "") else text


def _wav_bytes(audio: Pcm, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(audio)
    return buffer.getvalue()


def _multipart(boundary: str, model: str, language: str, audio: Pcm, sample_rate: int) -> bytes:
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(value.encode() + b"\r\n")

    field("model", model)
    if language:
        field("language", language)
    field("response_format", "json")

    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n')
    parts.append(b"Content-Type: audio/wav\r\n\r\n")
    parts.append(_wav_bytes(audio, sample_rate))
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def build_transcriber(config: Config) -> Transcriber:
    """Constrói o transcritor configurado. O modelo é descarregado na 1.ª vez."""
    settings = config.stt
    if settings.provider == "openai":
        import os

        api_key = os.environ.get(settings.cloud_api_key_env, "").strip()
        if not api_key:
            raise ModelError(
                f"stt.provider é 'openai' mas falta {settings.cloud_api_key_env} no .env"
            )
        return OpenAiTranscriber(
            settings.cloud_base_url,
            api_key,
            settings.cloud_model,
            language=settings.language,
            timeout=settings.timeout,
        )
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
