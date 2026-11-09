"""Janelas abertas: listar e focar."""

from __future__ import annotations

from typing import Any

from nox.desktop.guard import DesktopError
from nox.optional import require


def _windows() -> list[Any]:
    require("pygetwindow")
    import pygetwindow as gw

    return [
        window
        for window in gw.getAllWindows()
        if getattr(window, "title", "").strip() and getattr(window, "visible", True)
    ]


def list_windows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for window in _windows():
        rows.append(
            {
                "title": window.title,
                "left": getattr(window, "left", 0),
                "top": getattr(window, "top", 0),
                "width": getattr(window, "width", 0),
                "height": getattr(window, "height", 0),
                "active": bool(getattr(window, "isActive", False)),
            }
        )
    return rows


def focus(title: str) -> str:
    """Traz para a frente a primeira janela cujo título contenha `title`."""
    wanted = title.strip().lower()
    if not wanted:
        raise DesktopError("falta o título da janela")
    matches = [window for window in _windows() if wanted in window.title.lower()]
    if not matches:
        raise DesktopError(f"não encontrei nenhuma janela com {title!r}")
    window = matches[0]
    try:
        if getattr(window, "isMinimized", False):
            window.restore()
        window.activate()
    except Exception as exc:  # noqa: BLE001 — o Windows recusa algumas janelas
        raise DesktopError(f"não consegui focar {window.title!r}: {exc}") from exc
    return window.title
