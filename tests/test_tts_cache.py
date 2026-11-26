"""Testes da cache de voz e da sua ligação ao edge-tts."""

from __future__ import annotations

from pathlib import Path

from nox.speech import edge
from nox.speech.tts_cache import CacheDeVoz


def test_chave_muda_com_texto_voz_e_velocidade() -> None:
    base = CacheDeVoz.chave("Bom dia", "pt-PT-DuarteNeural", 1.0)
    assert base == CacheDeVoz.chave("  Bom   dia ", "pt-PT-DuarteNeural", 1.0)
    assert base != CacheDeVoz.chave("Bom dia", "pt-PT-RaquelNeural", 1.0)
    assert base != CacheDeVoz.chave("Bom dia", "pt-PT-DuarteNeural", 1.2)
    assert base != CacheDeVoz.chave("Boa noite", "pt-PT-DuarteNeural", 1.0)


def test_guardar_e_obter(tmp_path: Path) -> None:
    cache = CacheDeVoz(tmp_path)
    chave = CacheDeVoz.chave("olá", "voz", 1.0)
    assert cache.obter(chave) is None

    assert cache.guardar(chave, b"audio") is True
    assert cache.obter(chave) == b"audio"


def test_cache_vazia_nao_guarda(tmp_path: Path) -> None:
    cache = CacheDeVoz(tmp_path, limite_bytes=0)
    chave = CacheDeVoz.chave("x", "voz", 1.0)
    assert cache.guardar(chave, b"audio") is False
    assert cache.obter(chave) is None


def test_limite_apaga_os_mais_antigos(tmp_path: Path) -> None:
    cache = CacheDeVoz(tmp_path, limite_bytes=300)
    for indice in range(10):
        cache.guardar(CacheDeVoz.chave(f"frase {indice}", "voz", 1.0), b"x" * 100)

    assert cache.tamanho() <= 300
    assert len(cache.ficheiros()) <= 3


def test_synthesize_mp3_usa_cache(tmp_path: Path, monkeypatch) -> None:
    registo = CacheDeVoz(tmp_path, limite_bytes=10**6)
    chamadas: list[str] = []

    async def falso(text: str, voice: str, *, speed: float = 1.0) -> bytes:
        chamadas.append(text)
        return b"MP3-FALSO"

    monkeypatch.setattr(edge, "_download_mp3", falso)
    monkeypatch.setattr(edge, "require", lambda *args, **kwargs: None)

    primeiro = edge.synthesize_mp3("Bom dia.", "voz", cache=True, registo=registo)
    segundo = edge.synthesize_mp3("Bom dia.", "voz", cache=True, registo=registo)

    assert primeiro == segundo == b"MP3-FALSO"
    assert chamadas == ["Bom dia."]  # a segunda vez veio do disco


def test_sem_cache_chama_sempre(tmp_path: Path, monkeypatch) -> None:
    chamadas: list[str] = []

    async def falso(text: str, voice: str, *, speed: float = 1.0) -> bytes:
        chamadas.append(text)
        return b"MP3-FALSO"

    monkeypatch.setattr(edge, "_download_mp3", falso)
    monkeypatch.setattr(edge, "require", lambda *args, **kwargs: None)

    edge.synthesize_mp3("Bom dia.", "voz", cache=False)
    edge.synthesize_mp3("Bom dia.", "voz", cache=False)

    assert chamadas == ["Bom dia.", "Bom dia."]


def test_texto_vazio_nao_guarda_nada(tmp_path: Path, monkeypatch) -> None:
    registo = CacheDeVoz(tmp_path)
    monkeypatch.setattr(edge, "require", lambda *args, **kwargs: None)
    assert edge.synthesize_mp3("   ", "voz", cache=True, registo=registo) == b""
    assert registo.ficheiros() == []
