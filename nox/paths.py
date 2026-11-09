"""Resolução de caminhos em execução normal e empacotada."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "HeyNox"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """Diretório do executável (ou da raiz do projeto quando corre a partir do código)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    """Diretório de recursos embutidos pelo PyInstaller."""
    return Path(getattr(sys, "_MEIPASS", install_dir()))


def user_data_dir() -> Path:
    """Diretório de dados do utilizador. Windows: %LOCALAPPDATA%\\HeyNox."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / APP_NAME


def has_console() -> bool:
    """Falso quando o processo corre sem consola (pythonw ou PyInstaller windowed)."""
    return sys.stdout is not None and sys.stderr is not None
