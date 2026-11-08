from pathlib import Path

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
