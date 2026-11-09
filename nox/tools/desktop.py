"""Ferramenta de controlo do PC.

Uma ferramenta com ações. Ler o ecrã (janelas, captura, OCR) não pede nada;
mexer no rato, no teclado ou abrir apps pede aprovação e obedece ao botão de
emergência.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from nox.config import DesktopConfig
from nox.desktop import input as keyboard
from nox.desktop import screen, windows
from nox.desktop.guard import EMERGENCY, DesktopError
from nox.safety.approvals import ApprovalBroker
from nox.safety.sandbox import Sandbox
from nox.tools.base import ToolResult

MAX_LISTED_WINDOWS = 30


class DesktopTool:
    name = "desktop"
    description = (
        "Controla o PC. Leitura: 'windows' lista janelas, 'screenshot' captura o "
        "ecrã, 'ocr' lê texto da imagem. Ações: 'focus' (janela), 'click', "
        "'move', 'type', 'key' e 'open' (app permitida) — todas pedem aprovação. "
        "'stop' ativa o modo de emergência."
    )
    schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "windows",
                    "screenshot",
                    "ocr",
                    "focus",
                    "click",
                    "move",
                    "type",
                    "key",
                    "open",
                    "stop",
                ],
            },
            "window": {"type": "string", "description": "Título (ou parte) da janela"},
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "text": {"type": "string", "description": "Texto a escrever"},
            "keys": {"type": "string", "description": "Atalho, ex.: ctrl+s"},
            "app": {"type": "string", "description": "Executável permitido"},
            "path": {"type": "string", "description": "Imagem para OCR (opcional)"},
        },
        "required": ["action"],
    }

    def __init__(
        self,
        config: DesktopConfig,
        sandbox: Sandbox,
        *,
        approvals: ApprovalBroker | None = None,
    ) -> None:
        self._config = config
        self._sandbox = sandbox
        self._approvals = approvals

    # --- entrada ---------------------------------------------------------

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "").strip().lower()
        if action == "stop":
            EMERGENCY.trigger()
            return ToolResult(True, "modo de emergência ativo; controlo do PC parado")
        if not self._config.enabled:
            return ToolResult(False, "controlo do PC desligado (desktop.enabled: false)")
        try:
            EMERGENCY.check()
        except DesktopError as exc:
            return ToolResult(False, str(exc))

        try:
            return self._dispatch(action, arguments)
        except DesktopError as exc:
            return ToolResult(False, str(exc))

    def _dispatch(self, action: str, arguments: dict[str, Any]) -> ToolResult:
        if action == "windows":
            return self._windows()
        if action == "screenshot":
            return self._screenshot()
        if action == "ocr":
            return self._ocr(arguments)
        if action == "focus":
            return self._focus(str(arguments.get("window") or ""))
        if action == "click":
            return self._click(arguments)
        if action == "move":
            return self._move(arguments)
        if action == "type":
            return self._type(str(arguments.get("text") or ""))
        if action == "key":
            return self._key(str(arguments.get("keys") or ""))
        if action == "open":
            return self._open(str(arguments.get("app") or ""))
        return ToolResult(False, f"ação desconhecida: {action or '(vazia)'}")

    # --- leitura ---------------------------------------------------------

    def _windows(self) -> ToolResult:
        rows = windows.list_windows()[:MAX_LISTED_WINDOWS]
        if not rows:
            return ToolResult(True, "nenhuma janela visível")
        lines = []
        for row in rows:
            mark = " *" if row["active"] else ""
            lines.append(f"{row['title']}{mark} — {row['width']}x{row['height']}")
        return ToolResult(True, "\n".join(lines))

    def _screenshot(self) -> ToolResult:
        path = self._screenshot_path()
        screen.screenshot(path)
        return ToolResult(True, f"captura guardada em {path}")

    def _ocr(self, arguments: dict[str, Any]) -> ToolResult:
        raw = str(arguments.get("path") or "").strip()
        if raw:
            path = self._sandbox.resolve(raw)
            if not path.is_file():
                return ToolResult(False, f"{raw} não é um ficheiro")
        else:
            path = self._screenshot_path()
            screen.screenshot(path)
        text = screen.ocr(path)
        if not text:
            return ToolResult(True, "não encontrei texto na imagem")
        return ToolResult(True, text)

    # --- ações -----------------------------------------------------------

    def _focus(self, window: str) -> ToolResult:
        if not window:
            return ToolResult(False, "falta o título da janela")
        if not self._approve("focus", f"Focar a janela {window!r}", window):
            return ToolResult(False, f"não aprovado: focar {window!r}")
        return ToolResult(True, f"em foco: {windows.focus(window)}")

    def _click(self, arguments: dict[str, Any]) -> ToolResult:
        x, y = _coords(arguments)
        button = str(arguments.get("button") or "left")
        clicks = int(arguments.get("clicks") or 1)
        detail = f"Coordenadas: ({x}, {y})\nBotão: {button}\nCliques: {clicks}"
        if not self._approve("click", f"Clicar em ({x}, {y})", detail):
            return ToolResult(False, f"não aprovado: clique em ({x}, {y})")
        return ToolResult(True, keyboard.click(x, y, button=button, clicks=clicks))

    def _move(self, arguments: dict[str, Any]) -> ToolResult:
        x, y = _coords(arguments)
        if not self._approve("move", f"Mover o rato para ({x}, {y})", f"({x}, {y})"):
            return ToolResult(False, f"não aprovado: mover para ({x}, {y})")
        return ToolResult(True, keyboard.move(x, y))

    def _type(self, text: str) -> ToolResult:
        if not text:
            return ToolResult(False, "falta o texto")
        detail = f"Texto: {text[:500]}" + ("…" if len(text) > 500 else "")
        if not self._approve("type", f"Escrever {len(text)} caracteres", detail):
            return ToolResult(False, "não aprovado: escrever")
        return ToolResult(True, keyboard.type_text(text))

    def _key(self, keys: str) -> ToolResult:
        if not keys:
            return ToolResult(False, "falta a tecla")
        if not self._approve("key", f"Carregar em {keys}", keys):
            return ToolResult(False, f"não aprovado: {keys}")
        return ToolResult(True, keyboard.press(keys))

    def _open(self, app: str) -> ToolResult:
        app = app.strip()
        if not app:
            return ToolResult(False, "falta a aplicação")
        allowed = {name.lower() for name in self._config.allowed_apps}
        if app.lower() not in allowed:
            listed = ", ".join(self._config.allowed_apps) or "(nenhuma)"
            return ToolResult(
                False, f"{app} não está na lista de apps permitidas. Permitidas: {listed}"
            )
        if not self._approve("open", f"Abrir {app}", app):
            return ToolResult(False, f"não aprovado: abrir {app}")
        try:
            subprocess.Popen([app], shell=False)  # noqa: S603 — allowlist, sem shell
        except OSError as exc:
            raise DesktopError(f"não consegui abrir {app}: {exc}") from exc
        return ToolResult(True, f"{app} aberto")

    # --- apoio -----------------------------------------------------------

    def _approve(self, action: str, summary: str, detail: str) -> bool:
        if not self._config.confirm_actions:
            return True
        if self._approvals is None:
            raise DesktopError("esta ação precisa de aprovação na interface")
        return self._approvals.request(f"desktop:{action}", summary, detail)

    def _screenshot_path(self) -> Path:
        directory = self._sandbox.resolve(self._config.screenshot_dir)
        name = f"desktop-{datetime.now():%Y%m%d-%H%M%S}.png"
        return directory / name


def _coords(arguments: dict[str, Any]) -> tuple[int, int]:
    if "x" not in arguments or "y" not in arguments:
        raise DesktopError("faltam as coordenadas x e y")
    try:
        x = int(arguments["x"])
        y = int(arguments["y"])
    except (TypeError, ValueError) as exc:
        raise DesktopError("coordenadas inválidas") from exc
    if x < 0 or y < 0:
        raise DesktopError("coordenadas negativas")
    return x, y


def build_desktop_tools(
    config: DesktopConfig,
    sandbox: Sandbox,
    *,
    approvals: ApprovalBroker | None = None,
) -> list[Any]:
    return [DesktopTool(config, sandbox, approvals=approvals)]
