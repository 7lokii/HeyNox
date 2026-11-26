"""Medição de turnos: quanto tempo cada etapa leva.

O objetivo é simples: saber onde é que um turno gasta o tempo. Sem isto, baixar
a latência é adivinhar. Cada turno completo escreve uma linha no JSONL
(`<dados>/metrics/turnos.jsonl`), com os milissegundos de cada etapa.

O que **não** fica registado: o texto do pedido ou da resposta. Só o número de
caracteres, que chega para distinguir um "sim" de um parágrafo e não deixa a
conversa em disco. O ficheiro é local e roda ao chegar a 5 MB.
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ETAPAS = ("wake_ms", "stt_ms", "llm_ms", "tts_ms")
LIMITE_POR_OMISSAO = 5 * 1024 * 1024


@dataclass(frozen=True)
class Turno:
    """Um turno medido. Os `None` são etapas que não correram."""

    origem: str
    total_ms: float
    wake_ms: float | None = None
    stt_ms: float | None = None
    llm_ms: float | None = None
    tts_ms: float | None = None
    pedido_chars: int = 0
    resposta_chars: int = 0
    ok: bool = True
    erro: str = ""
    quando: str = ""

    def linha(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["quando"] = dados["quando"] or datetime.now(timezone.utc).isoformat()
        return dados


def _percentil(valores: list[float], fraccao: float) -> float:
    """Percentil por ordem, sem interpolação: com poucos turnos é mais honesto."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = max(0, min(len(ordenados) - 1, math.ceil(fraccao * len(ordenados)) - 1))
    return ordenados[indice]


class RegistoDeMetricas:
    """Escreve turnos em JSONL e resume os últimos N."""

    def __init__(
        self,
        caminho: Path | str,
        limite_bytes: int = LIMITE_POR_OMISSAO,
    ) -> None:
        self.caminho = Path(caminho)
        self.limite_bytes = limite_bytes
        self._cadeado = threading.Lock()

    def registar(self, turno: Turno) -> None:
        linha = turno.linha()
        try:
            with self._cadeado:
                self.caminho.parent.mkdir(parents=True, exist_ok=True)
                self._rodar_se_preciso()
                with self.caminho.open("a", encoding="utf-8") as saida:
                    saida.write(json.dumps(linha, ensure_ascii=False) + "\n")
        except OSError:
            # Não vale a pena estragar um turno por causa do registo.
            return

    def _rodar_se_preciso(self) -> None:
        try:
            if self.caminho.stat().st_size < self.limite_bytes:
                return
        except OSError:
            return
        anterior = self.caminho.with_suffix(self.caminho.suffix + ".1")
        anterior.unlink(missing_ok=True)
        self.caminho.rename(anterior)

    def _ler(self, ultimos: int) -> list[dict[str, Any]]:
        try:
            with self.caminho.open("r", encoding="utf-8") as entrada:
                linhas = entrada.readlines()
        except OSError:
            return []
        recortadas = linhas[-max(1, ultimos) :] if ultimos else linhas
        turnos: list[dict[str, Any]] = []
        for linha in recortadas:
            linha = linha.strip()
            if not linha:
                continue
            try:
                dados = json.loads(linha)
            except json.JSONDecodeError:
                # Uma linha meia escrita (o processo morreu a meio) não conta.
                continue
            if isinstance(dados, dict):
                turnos.append(dados)
        return turnos

    def resumo(self, ultimos: int = 200) -> dict[str, Any]:
        turnos = self._ler(ultimos)
        if not turnos:
            return {
                "turnos": 0,
                "falhas": 0,
                "ficheiro": str(self.caminho),
                "etapas": {},
            }

        etapas: dict[str, dict[str, float]] = {}
        for etapa in (*ETAPAS, "total_ms"):
            valores = [
                float(t[etapa])
                for t in turnos
                if isinstance(t.get(etapa), (int, float))
            ]
            if not valores:
                continue
            etapas[etapa] = {
                "media": round(sum(valores) / len(valores), 1),
                "p50": round(_percentil(valores, 0.5), 1),
                "p95": round(_percentil(valores, 0.95), 1),
                "max": round(max(valores), 1),
                "amostras": len(valores),
            }

        falhas = sum(1 for t in turnos if not t.get("ok", True))
        return {
            "turnos": len(turnos),
            "falhas": falhas,
            "desde": turnos[0].get("quando", ""),
            "ate": turnos[-1].get("quando", ""),
            "etapas": etapas,
            "ficheiro": str(self.caminho),
        }


def registo_por_omissao() -> RegistoDeMetricas:
    """O registo do serviço e do CLI, em `<dados>/metrics/turnos.jsonl`."""
    from nox.paths import user_data_dir

    return RegistoDeMetricas(user_data_dir() / "metrics" / "turnos.jsonl")
