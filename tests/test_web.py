import pytest

from nox.tools import web
from nox.tools.web import FetchUrlTool, WebSearchTool, html_to_text, validate_url

DDG_HTML = """
<html><body>
<div class="result results_links">
  <a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&amp;rut=1">Exemplo A</a>
  <a class="result__snippet" href="https://example.com/a">Resumo <b>do</b> A</a>
</div>
<div class="result results_links">
  <a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fb&amp;rut=2">Exemplo B</a>
  <a class="result__snippet" href="https://example.com/b">Resumo do B</a>
</div>
</body></html>
"""


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8765/api/state",
        "http://localhost:8000/",
        "http://192.168.1.1/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://nas.local/",
    ],
)
def test_private_addresses_are_refused(url: str) -> None:
    with pytest.raises(ValueError, match="rede local"):
        validate_url(url)


@pytest.mark.parametrize("url", ["file:///C:/Windows/win.ini", "ftp://example.com/x", ""])
def test_only_http_and_https(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url)


def test_public_address_passes() -> None:
    assert validate_url("https://example.com/a?b=1") == "https://example.com/a?b=1"


def test_html_to_text_drops_scripts_and_keeps_structure() -> None:
    markup = """
    <html><head><title>  Uma   notícia </title><style>p{color:red}</style></head>
    <body><h1>Manchete</h1><script>alert(1)</script>
    <p>Primeiro   parágrafo.</p><p>Segundo.</p></body></html>
    """
    title, text = html_to_text(markup)

    assert title == "Uma notícia"
    assert "Manchete" in text
    assert "Primeiro parágrafo." in text
    assert "alert" not in text
    assert "color:red" not in text


def test_search_parses_duckduckgo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web, "fetch", lambda url, timeout=15: ("https://ddg", DDG_HTML))

    results = web.search("exemplo", limit=2)

    assert [item["title"] for item in results] == ["Exemplo A", "Exemplo B"]
    assert [item["url"] for item in results] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert results[0]["snippet"] == "Resumo do A"


def test_search_tool_formats_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web, "fetch", lambda url, timeout=15: ("https://ddg", DDG_HTML))

    result = WebSearchTool().run({"query": "exemplo", "limit": 1})

    assert result.ok is True
    assert "1. Exemplo A" in result.content
    assert "https://example.com/a" in result.content


def test_search_tool_reports_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web, "fetch", lambda url, timeout=15: ("https://ddg", "<html></html>"))

    result = WebSearchTool().run({"query": "nada"})

    assert result.ok is True
    assert result.content == "sem resultados"


def test_fetch_tool_returns_title_and_text(monkeypatch: pytest.MonkeyPatch) -> None:
    page = "<html><head><title>Página</title></head><body><p>Conteúdo.</p></body></html>"
    monkeypatch.setattr(web, "fetch", lambda url, timeout=15: (url, page))

    result = FetchUrlTool().run({"url": "https://example.com"})

    assert result.ok is True
    assert result.content.startswith("Página\nhttps://example.com")
    assert "Conteúdo." in result.content


def test_fetch_tool_truncates_long_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    page = "<html><body><p>" + "a" * 8000 + "</p></body></html>"
    monkeypatch.setattr(web, "fetch", lambda url, timeout=15: (url, page))

    result = FetchUrlTool().run({"url": "https://example.com"})

    assert "… (truncado)" in result.content


def test_fetch_tool_reports_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, timeout: float = 15) -> tuple[str, str]:
        raise ValueError("sem ligação: teste")

    monkeypatch.setattr(web, "fetch", boom)

    result = FetchUrlTool().run({"url": "https://example.com"})

    assert result.ok is False
    assert "sem ligação" in result.content
