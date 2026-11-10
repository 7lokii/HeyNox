"""A janela nativa do HeyNox.

Uma janela própria, com ícone e barra de título, sobre o WebView2 que já existe
no Windows. Não é um separador do browser: fecha-se e leva o Nox com ela.

O `pywebview` tem de arrancar na thread principal, por isso `start()` bloqueia
até a janela fechar. Quem chama corre depois o encerramento do servidor.
"""

from __future__ import annotations

from nox.config import NoxError

TITLE = "Nox"
BACKGROUND = "#04070d"
WIDTH = 1280
HEIGHT = 820
MIN_SIZE = (980, 640)


def available() -> bool:
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return True


def open_window(url: str, *, title: str = TITLE) -> None:
    """Abre o HUD numa janela nativa e espera que o utilizador a feche."""
    try:
        import webview
    except ImportError as exc:  # pragma: no cover - falta o extra `shell`
        raise NoxError(
            'a janela do HeyNox precisa do extra `shell`: pip install -e ".[shell]"'
        ) from exc

    webview.create_window(
        title,
        url,
        width=WIDTH,
        height=HEIGHT,
        min_size=MIN_SIZE,
        background_color=BACKGROUND,
    )
    webview.start()
