"""Janelas do Windows via `ctypes`, sem dependências externas.

O `pygetwindow` não tem wheel e falhava a compilar no venv de build; a API do
Windows chega para listar e focar janelas, e não acrescenta nada ao pacote.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

from nox.desktop.guard import DesktopError

SW_RESTORE = 9


@dataclass
class Window:
    hwnd: int
    title: str
    left: int
    top: int
    width: int
    height: int
    active: bool


def _user32() -> ctypes.WinDLL:  # type: ignore[name-defined]
    if sys.platform != "win32":
        raise DesktopError("o controlo de janelas só está implementado no Windows")
    return ctypes.windll.user32  # type: ignore[attr-defined]


def _enumerate() -> list[Window]:
    user32 = _user32()
    windows: list[Window] = []
    foreground = user32.GetForegroundWindow()

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd: int, _param: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if not title:
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        windows.append(
            Window(
                hwnd=int(hwnd),
                title=title,
                left=int(rect.left),
                top=int(rect.top),
                width=int(rect.right - rect.left),
                height=int(rect.bottom - rect.top),
                active=hwnd == foreground,
            )
        )
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return windows


def list_windows() -> list[dict[str, object]]:
    return [
        {
            "title": window.title,
            "left": window.left,
            "top": window.top,
            "width": window.width,
            "height": window.height,
            "active": window.active,
        }
        for window in _enumerate()
    ]


def focus(title: str) -> str:
    """Traz para a frente a primeira janela cujo título contenha `title`."""
    wanted = title.strip().lower()
    if not wanted:
        raise DesktopError("falta o título da janela")
    matches = [window for window in _enumerate() if wanted in window.title.lower()]
    if not matches:
        raise DesktopError(f"não encontrei nenhuma janela com {title!r}")
    window = matches[0]
    user32 = _user32()
    try:
        if user32.IsIconic(window.hwnd):
            user32.ShowWindow(window.hwnd, SW_RESTORE)
        if not user32.SetForegroundWindow(window.hwnd):
            raise DesktopError(
                f"o Windows recusou focar {window.title!r}; clica na janela e tenta outra vez"
            )
    except DesktopError:
        raise
    except Exception as exc:  # noqa: BLE001 — API do Windows devolve erros variados
        raise DesktopError(f"não consegui focar {window.title!r}: {exc}") from exc
    return window.title
