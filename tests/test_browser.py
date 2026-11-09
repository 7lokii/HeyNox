import os
from pathlib import Path

import pytest

from nox.config import Config
from nox.optional import available
from nox.safety.sandbox import Sandbox
from nox.tools.browser import BrowserTool


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    config = Config.model_validate({"security": {"allowed_paths": [str(tmp_path)]}})
    return Sandbox(config, root=tmp_path)


def test_private_urls_are_refused_before_launching(sandbox: Sandbox) -> None:
    result = BrowserTool(sandbox).run({"url": "http://127.0.0.1:8765", "action": "text"})

    assert result.ok is False
    assert "rede local" in result.content


def test_unknown_action_is_refused(sandbox: Sandbox) -> None:
    result = BrowserTool(sandbox).run({"url": "https://example.com", "action": "voar"})

    assert result.ok is False
    assert "ação desconhecida" in result.content


def test_click_needs_approval_before_launching(sandbox: Sandbox) -> None:
    result = BrowserTool(sandbox).run(
        {"url": "https://example.com", "action": "click", "selector": "#botao"}
    )

    assert result.ok is False
    assert "aprovação" in result.content


def test_click_needs_a_selector(sandbox: Sandbox) -> None:
    result = BrowserTool(sandbox).run({"url": "https://example.com", "action": "click"})

    assert result.ok is False
    assert "seletor" in result.content


@pytest.mark.skipif(not available("playwright"), reason="extra browser não instalado")
@pytest.mark.skipif(
    not os.environ.get("NOX_SLOW_TESTS"), reason="precisa de rede e de NOX_SLOW_TESTS=1"
)
def test_browser_reads_a_real_page(sandbox: Sandbox) -> None:
    tool = BrowserTool(sandbox)
    try:
        result = tool.run({"url": "https://example.com", "action": "text"})
    finally:
        tool.close()

    assert result.ok is True
    assert "Example Domain" in result.content


@pytest.mark.skipif(not available("playwright"), reason="extra browser não instalado")
@pytest.mark.skipif(
    not os.environ.get("NOX_SLOW_TESTS"), reason="precisa de rede e de NOX_SLOW_TESTS=1"
)
def test_browser_saves_a_screenshot(sandbox: Sandbox, tmp_path: Path) -> None:
    tool = BrowserTool(sandbox)
    try:
        result = tool.run({"url": "https://example.com", "action": "screenshot"})
    finally:
        tool.close()

    assert result.ok is True
    shots = list((tmp_path / "data" / "screenshots").glob("*.png"))
    assert len(shots) == 1
    assert shots[0].stat().st_size > 1000
