import re
from pathlib import Path

import pytest

from nox.brain.llm import EchoLlm
from nox.main import main


def test_check_with_project_config(capsys) -> None:
    assert main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "Nox configurado (pt-PT)" in out


def test_check_with_custom_config(tmp_path: Path, capsys) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("nox:\n  wake_word: 'nox'\n  voice_enabled: false\n", encoding="utf-8")
    assert main(["--check", "--config", str(path)]) == 0
    assert "wake word 'nox'" in capsys.readouterr().out


def test_invalid_config_returns_code_2(tmp_path: Path, capsys) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("nox:\n  wake_word_sensitivity: -1\n", encoding="utf-8")
    assert main(["--config", str(path)]) == 2
    assert "Erro de configuração" in capsys.readouterr().err


def test_no_warning_when_voice_disabled(tmp_path: Path, capsys) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("nox:\n  voice_enabled: false\n", encoding="utf-8")
    main(["--check", "--config", str(path)])
    assert "Modo voz" not in capsys.readouterr().err


def test_windowed_mode_logs_instead_of_printing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nox.main.user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nox.main.has_console", lambda: False)
    assert main(["--check"]) == 0
    log = (tmp_path / "logs" / "nox.log").read_text(encoding="utf-8")
    assert "Nox configurado (pt-PT)" in log


def test_windowed_mode_logs_unexpected_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("nox.main.user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nox.main.has_console", lambda: False)

    def boom(*_args, **_kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("nox.main.load_config", boom)
    assert main(["--check"]) == 1
    log = (tmp_path / "logs" / "nox.log").read_text(encoding="utf-8")
    assert "RuntimeError: falha simulada" in log


def test_say_answers_local_question(capsys) -> None:
    assert main(["--say", "que horas são?"]) == 0
    assert re.match(r"(São|É) \d+h\d{2}\.", capsys.readouterr().out.strip())


def test_say_uses_the_model(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr("nox.main.build_llm", lambda config: EchoLlm())
    assert main(["--say", "olá"]) == 0
    assert "(eco) olá" in capsys.readouterr().out


def test_say_without_key_explains_what_is_missing(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr("nox.main.load_environment", lambda *args, **kwargs: None)
    monkeypatch.delenv("NOX_LLM_API_KEY", raising=False)
    assert main(["--say", "quem és tu?"]) == 2
    assert "Erro:" in capsys.readouterr().err


def test_text_session_exits_on_sair(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr("nox.main.build_llm", lambda config: EchoLlm())
    answers = iter(["olá", "sair"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert main(["--text"]) == 0
    assert "Nox: (eco) olá" in capsys.readouterr().out
