"""Testes da medição de turnos (nox/metrics.py)."""

from __future__ import annotations

import json
from pathlib import Path

from nox.metrics import RegistoDeMetricas, Turno


def _turno(total: float, stt: float = 100.0, llm: float = 50.0) -> Turno:
    return Turno(
        origem="hud",
        stt_ms=stt,
        llm_ms=llm,
        total_ms=total,
        pedido_chars=10,
        resposta_chars=20,
    )


def test_registar_escreve_uma_linha_por_turno(tmp_path: Path) -> None:
    registo = RegistoDeMetricas(tmp_path / "metrics" / "turnos.jsonl")
    registo.registar(_turno(200))
    registo.registar(_turno(400))

    linhas = (tmp_path / "metrics" / "turnos.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2
    primeiro = json.loads(linhas[0])
    assert primeiro["origem"] == "hud"
    assert primeiro["total_ms"] == 200
    assert primeiro["quando"]  # preenchido na escrita


def test_resumo_calcula_media_e_percentis(tmp_path: Path) -> None:
    registo = RegistoDeMetricas(tmp_path / "turnos.jsonl")
    for total in (100, 200, 300, 400, 1000):
        registo.registar(_turno(float(total)))

    resumo = registo.resumo()
    assert resumo["turnos"] == 5
    assert resumo["falhas"] == 0
    assert resumo["etapas"]["total_ms"]["media"] == 400.0
    assert resumo["etapas"]["total_ms"]["p50"] == 300.0
    assert resumo["etapas"]["total_ms"]["p95"] == 1000.0
    assert resumo["etapas"]["total_ms"]["max"] == 1000.0
    assert resumo["etapas"]["stt_ms"]["amostras"] == 5


def test_resumo_sem_turnos(tmp_path: Path) -> None:
    resumo = RegistoDeMetricas(tmp_path / "nao-existe.jsonl").resumo()
    assert resumo["turnos"] == 0
    assert resumo["etapas"] == {}


def test_linha_corrompida_e_ignorada(tmp_path: Path) -> None:
    caminho = tmp_path / "turnos.jsonl"
    registo = RegistoDeMetricas(caminho)
    registo.registar(_turno(150))
    with caminho.open("a", encoding="utf-8") as saida:
        saida.write('{"total_ms": 9')  # processo morto a meio da escrita

    resumo = registo.resumo()
    assert resumo["turnos"] == 1


def test_falhas_contam_e_nao_entram_nas_etapas(tmp_path: Path) -> None:
    registo = RegistoDeMetricas(tmp_path / "turnos.jsonl")
    registo.registar(_turno(200))
    registo.registar(
        Turno(
            origem="hud",
            stt_ms=90.0,
            total_ms=95.0,
            pedido_chars=5,
            ok=False,
            erro="o modelo falhou",
        )
    )

    resumo = registo.resumo()
    assert resumo["turnos"] == 2
    assert resumo["falhas"] == 1
    assert resumo["etapas"]["llm_ms"]["amostras"] == 1


def test_roda_o_ficheiro_ao_passar_o_limite(tmp_path: Path) -> None:
    caminho = tmp_path / "turnos.jsonl"
    registo = RegistoDeMetricas(caminho, limite_bytes=200)
    for _ in range(10):
        registo.registar(_turno(123.0))

    assert caminho.exists()
    assert (tmp_path / "turnos.jsonl.1").exists()
    # O ficheiro atual ficou pequeno outra vez, e o antigo guarda o resto.
    assert registo.resumo(ultimos=1000)["turnos"] >= 1


def test_ultimos_limita_a_leitura(tmp_path: Path) -> None:
    registo = RegistoDeMetricas(tmp_path / "turnos.jsonl")
    for total in (100, 500, 900):
        registo.registar(_turno(float(total)))

    resumo = registo.resumo(ultimos=1)
    assert resumo["turnos"] == 1
    assert resumo["etapas"]["total_ms"]["media"] == 900.0
