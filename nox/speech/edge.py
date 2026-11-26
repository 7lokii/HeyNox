"""Vozes neurais da Microsoft (edge-tts).

Não é local: o texto sai do PC e o áudio vem da rede. Fica como opção, não como
padrão — quem quer o Nox offline usa o Piper.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

from nox.audio.types import Pcm
from nox.config import NoxError
from nox.optional import require
from nox.speech.tts_cache import CacheDeVoz, cache_por_omissao

EDGE_SAMPLE_RATE = 24000


class EdgeError(NoxError):
    """A voz neural não respondeu ou devolveu áudio inválido."""


class EdgeSynthesizer:
    """`pt-PT-DuarteNeural` (masculino) e `pt-PT-RaquelNeural` (feminino)."""

    sample_rate = EDGE_SAMPLE_RATE

    def __init__(
        self,
        voice: str = "pt-PT-DuarteNeural",
        *,
        speed: float = 1.0,
        cache: bool = True,
    ) -> None:
        require("edge_tts")
        self._voice = voice
        self._speed = speed
        self._cache = cache

    def synthesize(self, text: str) -> Pcm:
        text = text.strip()
        if not text:
            return Pcm(b"")
        return _decode_mp3(
            synthesize_mp3(
                text, self._voice, speed=self._speed, cache=self._cache
            )
        )


def synthesize_mp3(
    text: str,
    voice: str = "pt-PT-DuarteNeural",
    *,
    speed: float = 1.0,
    cache: bool = True,
    registo: CacheDeVoz | None = None,
) -> bytes:
    """Sintetiza para MP3, sem descodificar.

    O HUD remoto toca o ficheiro no browser; não precisa de PCM nem do PyAV.
    Com `cache`, a mesma frase não volta a ir à rede: o áudio fica em disco e a
    segunda chamada é uma leitura local. A cache é verificada antes de exigir o
    `edge_tts`, para servir áudio já gerado mesmo numa máquina sem a biblioteca.
    """
    text = text.strip()
    if not text:
        return b""
    guardado: CacheDeVoz | None = None
    chave = ""
    if cache:
        guardado = registo or cache_por_omissao()
        chave = CacheDeVoz.chave(text, voice, speed)
        existente = guardado.obter(chave, ".mp3")
        if existente is not None:
            return existente
    require("edge_tts")
    try:
        audio = asyncio.run(_download_mp3(text, voice, speed=speed))
    except EdgeError:
        raise
    except Exception as exc:  # aiohttp e websockets falham de formas variadas
        raise EdgeError(f"a voz neural falhou: {exc}") from exc
    if guardado is not None and audio:
        guardado.guardar(chave, audio, ".mp3")
    return audio


async def _download_mp3(text: str, voice: str, *, speed: float = 1.0) -> bytes:
    import edge_tts

    # O edge-tts usa percentagens: +20% é 1,2x mais rápido.
    rate = f"{round((speed - 1.0) * 100):+d}%"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    chunks: list[bytes] = []
    async for event in communicate.stream():
        if event["type"] != "audio":
            continue
        data = event.get("data")
        if isinstance(data, bytes):
            chunks.append(data)
    if not chunks:
        raise EdgeError("a voz neural não devolveu áudio")
    return b"".join(chunks)


def _decode_mp3(data: bytes) -> Pcm:
    """MP3 -> PCM 16 bits mono. Usa o PyAV que já vem com o faster-whisper."""
    require("av")
    import av

    chunks: list[bytes] = []
    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=EDGE_SAMPLE_RATE)
        # Os stubs do PyAV não expõem decode() no contentor.
        for frame in container.decode(stream):  # pyright: ignore[reportAttributeAccessIssue]
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray().tobytes())
    if not chunks:
        raise EdgeError("não consegui descodificar o áudio da voz neural")
    return Pcm(b"".join(chunks))


def list_voices() -> list[Any]:
    """Vozes pt-PT disponíveis, para diagnóstico."""
    require("edge_tts")
    import edge_tts

    async def collect() -> list[Any]:
        return [v for v in await edge_tts.list_voices() if v["Locale"].startswith("pt-PT")]

    return asyncio.run(collect())
