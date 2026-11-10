"""Ícone na bandeja do Windows.

O executável não tem janela própria: se o browser for fechado, não sobra nada
visível para reabrir a interface nem para o fechar. O `pystray` corre o seu
próprio `SystrayIcon` numa thread, por isso o `serve()` pode bloquear no
`run()` da bandeja em vez do `serve_forever()` do HTTP.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from importlib import import_module
from pathlib import Path
from typing import Any

from nox.optional import require
from nox.paths import bundle_dir, install_dir

ICON_NAME = "HeyNox"
OPEN = "Abrir interface"
QUIT = "Sair"


def icon_path() -> Path | None:
    for candidate in (
        install_dir() / "icon.ico",
        bundle_dir() / "icon.ico",
        install_dir().parent / "installer" / "icon.ico",
    ):
        if candidate.is_file():
            return candidate
    return None


def _image() -> Any:
    Image = import_module("PIL.Image")
    path = icon_path()
    if path is None:
        return Image.new("RGBA", (64, 64), (4, 18, 26, 255))
    with Image.open(path) as opened:
        return opened.convert("RGBA")


class Tray:
    """Ícone com «Abrir interface», «Ouvir» e «Sair»."""

    def __init__(
        self,
        ui_url: str,
        *,
        on_open: Callable[[], None],
        on_toggle_voice: Callable[[bool], None],
        on_quit: Callable[[], None],
        voice_on: bool = False,
    ) -> None:
        self.ui_url = ui_url
        self.on_open = on_open
        self.on_toggle_voice = on_toggle_voice
        self.on_quit = on_quit
        self._voice = voice_on
        pystray = require("pystray")
        self._pystray = pystray
        self.icon = pystray.Icon(ICON_NAME, _image(), self._title(), self._menu())

    def _title(self) -> str:
        estado = "a ouvir" if self._voice else "parado"
        return f"{ICON_NAME} — {estado} — {self.ui_url}"

    def _menu(self) -> Any:
        pystray = self._pystray
        return pystray.Menu(
            pystray.MenuItem(OPEN, self._open, default=True),
            pystray.MenuItem("Ouvir", self._toggle_voice, checked=lambda _item: self._voice),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(QUIT, self._exit),
        )

    def _open(self, *_args: object) -> None:
        self.on_open()

    def _toggle_voice(self, *_args: object) -> None:
        wanted = not self._voice
        try:
            self.on_toggle_voice(wanted)
        except Exception:  # noqa: BLE001 — a voz pode falhar sem derrubar a bandeja
            wanted = self._voice
        self.set_voice(wanted)

    def _exit(self, *_args: object) -> None:
        try:
            self.on_quit()
        finally:
            self.icon.stop()

    def notify(self, message: str, title: str = ICON_NAME) -> None:
        """Balão da bandeja. Sem foco assistido (`ACA`) o Windows come-o em silêncio."""
        with suppress(Exception):
            self.icon.notify(message[:255], title)

    def set_voice(self, running: bool) -> None:
        if running == self._voice:
            return
        self._voice = running
        with suppress(Exception):  # ícone ainda não visível
            self.icon.update_menu()
            self.icon.title = self._title()

    def run(self) -> None:
        """Bloqueia até «Sair»."""
        self.icon.run()

    def stop(self) -> None:
        with suppress(Exception):
            self.icon.stop()
