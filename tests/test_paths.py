import sys
from pathlib import Path

import pytest

from nox import paths


def test_install_dir_is_project_root_when_not_frozen() -> None:
    assert not paths.is_frozen()
    assert paths.install_dir() == Path(paths.__file__).resolve().parent.parent


def test_user_data_dir_follows_localappdata_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.user_data_dir() == tmp_path / "HeyNox"


def test_user_data_dir_follows_xdg_on_linux(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert paths.user_data_dir() == tmp_path / "HeyNox"


def test_frozen_bundle_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "nox.exe"))
    assert paths.is_frozen()
    assert paths.install_dir() == tmp_path
    assert paths.bundle_dir() == tmp_path


def test_has_console_detects_windowed_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    assert paths.has_console() is True
    monkeypatch.setattr(sys, "stdout", None)
    assert paths.has_console() is False
