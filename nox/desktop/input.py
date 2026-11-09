"""Teclado e rato. Tudo passa por aqui para haver um único ponto de travão."""

from __future__ import annotations

from typing import Any

from nox.desktop.guard import EMERGENCY, DesktopError
from nox.optional import require

MAX_TEXT = 2000

_MODIFIERS = {"ctrl", "alt", "shift", "win"}
_NAMED = {
    "enter",
    "tab",
    "esc",
    "space",
    "backspace",
    "delete",
    "insert",
    "home",
    "end",
    "pageup",
    "pagedown",
    "up",
    "down",
    "left",
    "right",
    "capslock",
    *(f"f{number}" for number in range(1, 13)),
}


def _gui() -> Any:
    require("pyautogui")
    import pyautogui

    pyautogui.FAILSAFE = True  # rato no canto superior esquerdo aborta
    pyautogui.PAUSE = 0.05
    return pyautogui


def _check() -> None:
    EMERGENCY.check()


def move(x: int, y: int) -> str:
    _check()
    if x < 0 or y < 0:
        raise DesktopError("coordenadas negativas")
    _gui().moveTo(x, y, duration=0.2)
    return f"rato em ({x}, {y})"


def click(x: int, y: int, *, button: str = "left", clicks: int = 1) -> str:
    _check()
    if button not in {"left", "right", "middle"}:
        raise DesktopError(f"botão inválido: {button}")
    if not 1 <= clicks <= 3:
        raise DesktopError("número de cliques inválido")
    gui = _gui()
    gui.click(x=x, y=y, button=button, clicks=clicks, interval=0.12)
    return f"{clicks} clique(s) {button} em ({x}, {y})"


def type_text(text: str) -> str:
    _check()
    if not text:
        raise DesktopError("falta o texto")
    if len(text) > MAX_TEXT:
        raise DesktopError(f"o texto é grande demais ({len(text)} caracteres)")
    require("pyperclip")
    import pyperclip

    gui = _gui()
    try:
        previous = pyperclip.paste()
    except Exception:  # noqa: BLE001 — clipboard indisponível
        previous = None
    pyperclip.copy(text)
    try:
        gui.hotkey("ctrl", "v")
    finally:
        if previous is not None:
            pyperclip.copy(previous)
    return f"escrevi {len(text)} caracteres"


def press(keys: str) -> str:
    _check()
    raw = [part.strip().lower() for part in keys.split("+") if part.strip()]
    if not raw:
        raise DesktopError("falta a tecla")
    if len(raw) > 4:
        raise DesktopError("demasiadas teclas de uma vez")
    for key in raw:
        if key not in _MODIFIERS and key not in _NAMED and not (len(key) == 1 and key.isalnum()):
            raise DesktopError(f"tecla não permitida: {key}")
    _gui().hotkey(*raw)
    return "teclas: " + "+".join(raw)
