"""Cache de áudio sintetizado.

Sintetizar a mesma frase duas vezes é desperdício: "que horas são" e "bom dia"
repetem-se todos os dias, e no `edge` cada repetição é uma ida à rede (cerca de
1,2 s, medido em `/api/metrics`). Aqui o áudio fica em disco, endereçado pelo
hash de (texto, voz, velocidade), e a segunda vez é uma leitura local.

O que fica em disco é áudio do assistente, nunca do utilizador. A cache não tem
nada de privado: a mesma frase dá sempre o mesmo ficheiro.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

LIMITE_POR_OMISSAO = 64 * 1024 * 1024


class CacheDeVoz:
    """Áudio por hash, com um teto de espaço em disco."""

    def __init__(self, raiz: Path | str, limite_bytes: int = LIMITE_POR_OMISSAO) -> None:
        self.raiz = Path(raiz)
        self.limite_bytes = max(0, limite_bytes)

    @staticmethod
    def chave(texto: str, voz: str, velocidade: float = 1.0) -> str:
        """Hash do que muda o áudio. O texto entra normalizado nos espaços."""
        base = f"{voz}\x00{velocidade:.3f}\x00{' '.join(texto.split())}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def _caminho(self, chave: str, extensao: str) -> Path:
        return self.raiz / chave[:2] / chave[2:4] / f"{chave}{extensao}"

    def obter(self, chave: str, extensao: str = ".mp3") -> bytes | None:
        caminho = self._caminho(chave, extensao)
        try:
            dados = caminho.read_bytes()
        except OSError:
            return None
        if not dados:
            return None
        # Um toque no mtime mantém o ficheiro usado longe da limpeza.
        try:
            os.utime(caminho, None)
        except OSError:
            pass
        return dados

    def guardar(self, chave: str, dados: bytes, extensao: str = ".mp3") -> bool:
        if not dados or self.limite_bytes == 0:
            return False
        caminho = self._caminho(chave, extensao)
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            temporario = caminho.with_suffix(caminho.suffix + ".tmp")
            temporario.write_bytes(dados)
            os.replace(temporario, caminho)
        except OSError:
            return False
        self.limpar()
        return True

    def ficheiros(self) -> list[tuple[Path, int, float]]:
        """Todos os ficheiros da cache: caminho, tamanho e mtime."""
        encontrados: list[tuple[Path, int, float]] = []
        if not self.raiz.is_dir():
            return encontrados
        for caminho in self.raiz.rglob("*"):
            if not caminho.is_file() or caminho.suffix == ".tmp":
                continue
            try:
                estado = caminho.stat()
            except OSError:
                continue
            encontrados.append((caminho, estado.st_size, estado.st_mtime))
        return encontrados

    def tamanho(self) -> int:
        return sum(tamanho for _, tamanho, _ in self.ficheiros())

    def limpar(self) -> int:
        """Apaga os mais antigos até caber no limite. Devolve quantos saíram."""
        ficheiros = self.ficheiros()
        total = sum(tamanho for _, tamanho, _ in ficheiros)
        if total <= self.limite_bytes:
            return 0
        removidos = 0
        # Deixa 90% de folga para não andar a limpar a cada escrita.
        alvo = int(self.limite_bytes * 0.9)
        for caminho, tamanho, _ in sorted(ficheiros, key=lambda item: item[2]):
            if total <= alvo:
                break
            try:
                caminho.unlink()
            except OSError:
                continue
            total -= tamanho
            removidos += 1
        return removidos


def cache_por_omissao() -> CacheDeVoz:
    """A cache do serviço e do CLI, em `<dados>/tts`."""
    from nox.config import load_config

    limite_mb = 64
    try:
        limite_mb = load_config().tts.cache_max_mb
    except Exception:  # noqa: BLE001 - sem config, usa o limite por omissão
        limite_mb = 64
    return CacheDeVoz(_pasta(), limite_mb * 1024 * 1024)


def _pasta() -> Path:
    from nox.paths import user_data_dir

    return user_data_dir() / "tts"


def agora() -> float:
    return time.time()
