"""Browser real (Chromium headless) para páginas que não são HTML simples.

Ler o texto de uma página com `fetch_url` chega para quase tudo. Este browser
existe para o resto: páginas montadas por JavaScript, capturas de ecrã e listas
de links. É só leitura — clicar e escrever fica para a Fase 5.

O browser arranca na primeira utilização e fica vivo entre pedidos: lançar um
Chromium por chamada somava segundos a cada resposta.
"""

from __future__ import annotations

import atexit
import contextlib
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from nox.safety.approvals import ApprovalBroker
from nox.safety.sandbox import Sandbox
from nox.tools.base import ToolResult
from nox.tools.web import MAX_TEXT, validate_url

MAX_LINKS = 40


class BrowserTool:
    name = "browser"
    description = (
        "Abre uma página num browser real (headless). Ações: 'text' devolve o "
        "texto visível, 'links' lista os links, 'screenshot' guarda uma imagem "
        "em data/screenshots, 'click' e 'fill' interagem com a página (pedem "
        "aprovação). Usa quando fetch_url não chega (páginas com JavaScript)."
    )
    schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Endereço http(s)"},
            "action": {
                "type": "string",
                "enum": ["text", "links", "screenshot", "click", "fill"],
                "description": "O que fazer na página",
            },
            "selector": {"type": "string", "description": "Seletor CSS (click/fill)"},
            "text": {"type": "string", "description": "Texto a escrever (fill)"},
        },
        "required": ["url"],
    }

    def __init__(
        self,
        sandbox: Sandbox,
        *,
        headless: bool = True,
        timeout_ms: int = 20000,
        approvals: ApprovalBroker | None = None,
        confirm_actions: bool = True,
    ) -> None:
        self._sandbox = sandbox
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._approvals = approvals
        self._confirm = confirm_actions
        self._lock = threading.Lock()
        self._playwright: Any = None
        self._browser: Any = None
        atexit.register(self.close)

    # --- ciclo de vida ---------------------------------------------------

    def _ensure_browser(self) -> Any:
        if self._browser is not None:
            return self._browser
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError('o browser precisa do extra: pip install -e ".[browser]"') from exc
        self._playwright = sync_playwright().start()
        # `channel="chromium"` usa o Chrome for Testing completo. O binário
        # "headless shell" é outro download e pode não estar instalado.
        try:
            self._browser = self._playwright.chromium.launch(
                headless=self._headless, channel="chromium"
            )
        except Exception:  # noqa: BLE001
            try:
                self._browser = self._playwright.chromium.launch(headless=self._headless)
            except Exception as exc:  # noqa: BLE001
                self._playwright.stop()
                self._playwright = None
                raise RuntimeError(
                    "não consegui lançar o Chromium. Corre: python -m playwright install chromium"
                ) from exc
        return self._browser

    def _stop(self) -> None:
        with contextlib.suppress(Exception):  # fechar nunca pode rebentar
            if self._browser is not None:
                self._browser.close()
        with contextlib.suppress(Exception):
            if self._playwright is not None:
                self._playwright.stop()
        self._browser = None
        self._playwright = None

    def close(self) -> None:
        with self._lock:
            self._stop()

    # --- ações -----------------------------------------------------------

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        url = str(arguments.get("url", "")).strip()
        action = str(arguments.get("action") or "text").strip().lower()
        if action not in {"text", "links", "screenshot", "click", "fill"}:
            return ToolResult(False, f"ação desconhecida: {action}")
        selector = str(arguments.get("selector") or "").strip()
        text = str(arguments.get("text") or "")
        if action in {"click", "fill"} and not selector:
            return ToolResult(False, "falta o seletor")
        try:
            target = validate_url(url)
        except ValueError as exc:
            return ToolResult(False, str(exc))
        if action in {"click", "fill"} and self._confirm:
            if self._approvals is None:
                return ToolResult(False, "interagir com a página precisa de aprovação na interface")
            summary = (
                f"Clicar em {selector} em {target}"
                if action == "click"
                else f"Escrever em {selector} em {target}"
            )
            detail = f"Ação: {action}\nPágina: {target}\nSeletor: {selector}"
            if action == "fill":
                detail += f"\nTexto: {text[:500]}"
            if not self._approvals.request("browser", summary, detail):
                return ToolResult(False, f"não aprovado: {action} em {target}")

        with self._lock:
            try:
                browser = self._ensure_browser()
                page = browser.new_page(viewport={"width": 1280, "height": 800})
            except RuntimeError as exc:
                return ToolResult(False, str(exc))
            except Exception as exc:  # noqa: BLE001 — falha ao lançar o Chromium
                self._stop()
                return ToolResult(False, f"não consegui lançar o browser: {exc}")

            try:
                page.goto(target, wait_until="domcontentloaded", timeout=self._timeout_ms)
                if action == "links":
                    return self._links(page, target)
                if action == "screenshot":
                    return self._screenshot(page, target)
                if action == "click":
                    page.click(selector, timeout=5000)
                    return ToolResult(True, f"cliquei em {selector} em {target}")
                if action == "fill":
                    page.fill(selector, text, timeout=5000)
                    return ToolResult(True, f"escrevi em {selector} em {target}")
                return self._text(page, target)
            except Exception as exc:  # noqa: BLE001 — erro do Playwright
                message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                if "Timeout" in type(exc).__name__:
                    message = "a página demorou demasiado a abrir"
                self._stop()
                return ToolResult(False, f"o browser falhou: {message}")
            finally:
                with contextlib.suppress(Exception):
                    page.close()

    def _text(self, page: Any, target: str) -> ToolResult:
        title = page.title()
        text = page.inner_text("body") or ""
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + "\n… (truncado)"
        header = f"{title}\n{target}" if title else target
        return ToolResult(True, f"{header}\n\n{text}" if text else header)

    def _links(self, page: Any, target: str) -> ToolResult:
        entries = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
        )
        lines: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            href = str(entry.get("href", "")).strip()
            if not href.startswith(("http://", "https://")) or href in seen:
                continue
            seen.add(href)
            label = re.sub(r"\s+", " ", str(entry.get("text", ""))).strip() or "(sem texto)"
            lines.append(f"- {label}: {href}")
            if len(lines) >= MAX_LINKS:
                break
        return ToolResult(True, "\n".join(lines) or f"sem links em {target}")

    def _screenshot(self, page: Any, target: str) -> ToolResult:
        directory = self._sandbox.resolve("data/screenshots")
        directory.mkdir(parents=True, exist_ok=True)
        host = re.sub(r"[^a-z0-9]+", "-", urlsplit(target).hostname or "pagina").strip("-")
        name = f"{host}-{datetime.now():%Y%m%d-%H%M%S}.png"
        path: Path = directory / name
        page.screenshot(path=str(path), full_page=False)
        return ToolResult(True, f"captura guardada em {path}")


def build_browser_tools(sandbox: Sandbox, *, approvals: ApprovalBroker | None = None) -> list[Any]:
    return [BrowserTool(sandbox, approvals=approvals)]
