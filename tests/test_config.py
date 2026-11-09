import os
from pathlib import Path

import pytest

from nox.config import (
    DEFAULT_CONFIG_PATH,
    Config,
    ConfigError,
    data_dir,
    load_config,
    load_environment,
)


def test_project_config_is_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nox.config.user_data_dir", lambda: tmp_path / "user")
    config = load_config()
    assert config.nox.name == "Nox"
    assert config.nox.wake_word == "hey nox"
    assert config.nox.language == "pt-PT"


def test_spec_defaults_match_yaml() -> None:
    config = load_config(DEFAULT_CONFIG_PATH)
    assert config.audio.sample_rate == 16000
    assert config.stt.model == "small"
    assert config.github.default_repo == "7lokii/HeyNox"
    assert config.security.allowed_commands[:2] == ["git status", "git diff"]
    assert "delete" in config.security.require_confirmation


def test_security_defaults_are_restrictive() -> None:
    config = Config()
    assert config.github.allow_push_to_main is False
    assert ".env" in config.security.blocked_paths
    assert config.github.require_pr is True


def test_minimal_config_uses_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("nox:\n  wake_word: 'nox'\n", encoding="utf-8")
    config = load_config(path)
    assert config.nox.wake_word == "nox"
    assert config.nox.name == "Nox"
    assert config.tts.provider == "piper"


@pytest.mark.parametrize(
    "body",
    [
        "nox:\n  wake_word: ''\n",
        "nox:\n  wake_word_sensitivity: 1.5\n",
        "audio:\n  sample_rate: 0\n",
        "tts:\n  provider: 'festival'\n",
        "security:\n  require_confirmation: ['do_everything']\n",
    ],
)
def test_invalid_config_raises(tmp_path: Path, body: str) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="não encontrado"):
        load_config(tmp_path / "inexistente.yaml")


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("nox: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_config(path)


def test_top_level_must_be_mapping(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("- item\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapa"):
        load_config(path)


def test_empty_config_file_uses_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    assert load_config(path).nox.name == "Nox"


def test_env_does_not_override_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("NOX_TEST_FLAG=from_file\nNOX_DATA_DIR=./do_file\n", encoding="utf-8")
    monkeypatch.setenv("NOX_DATA_DIR", "./from_env")
    monkeypatch.delenv("NOX_TEST_FLAG", raising=False)
    load_environment(env_file)
    assert os.environ["NOX_DATA_DIR"] == "./from_env"
    assert os.environ["NOX_TEST_FLAG"] == "from_file"
    assert data_dir().name == "from_env"


def test_explicit_env_file_wins_over_globals(tmp_path: Path, monkeypatch) -> None:
    global_env = tmp_path / ".env"
    global_env.write_text("NOX_EXPLICIT_FLAG=global\n", encoding="utf-8")
    explicit_env = tmp_path / "custom.env"
    explicit_env.write_text("NOX_EXPLICIT_FLAG=custom\n", encoding="utf-8")
    monkeypatch.setattr("nox.config.user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("nox.config.PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("NOX_EXPLICIT_FLAG", raising=False)
    load_environment(explicit_env)
    assert os.environ["NOX_EXPLICIT_FLAG"] == "custom"


def test_user_config_preferred_when_present(tmp_path: Path, monkeypatch) -> None:
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "config.yaml").write_text("nox:\n  wake_word: 'user nox'\n", encoding="utf-8")
    monkeypatch.setattr("nox.config.user_data_dir", lambda: user_dir)
    assert load_config().nox.wake_word == "user nox"


def test_explicit_path_beats_user_config(tmp_path: Path, monkeypatch) -> None:
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "config.yaml").write_text("nox:\n  wake_word: 'user nox'\n", encoding="utf-8")
    monkeypatch.setattr("nox.config.user_data_dir", lambda: user_dir)
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("nox:\n  wake_word: 'explicit nox'\n", encoding="utf-8")
    assert load_config(explicit).nox.wake_word == "explicit nox"
