"""O HUD compilado: procura, resolução de estáticos e defesa contra `..`.

`nox/ui/static.py` decide o que a janela mostra. Estes testes fixam as quatro
regras: o build manda, o legado serve de rede, os tipos MIME estão certos e um
caminho com `..` não sai da raiz.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nox.ui import static as hud


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Um `ui/dist` falso, com index, um asset e um favicon."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<title>Nox</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setenv("NOX_UI_DIST", str(dist))
    return dist


def test_dist_dir_prefers_the_override(build: Path) -> None:
    assert hud.dist_dir() == build


def test_index_file_is_the_build(build: Path) -> None:
    assert hud.index_file() == build / "index.html"


def test_resolve_serves_the_build_assets(build: Path) -> None:
    found = hud.resolve("/assets/app.js")
    assert found is not None
    path, content_type = found
    assert path == build / "assets" / "app.js"
    assert content_type == "text/javascript; charset=utf-8"


def test_resolve_maps_the_root_to_index(build: Path) -> None:
    for url in ("/", "/index.html"):
        found = hud.resolve(url)
        assert found is not None
        assert found[0] == build / "index.html"
        assert found[1] == "text/html; charset=utf-8"


def test_resolve_refuses_to_leave_the_root(build: Path) -> None:
    assert hud.resolve("/../secrets.env") is None
    assert hud.resolve("/assets/../../secrets.env") is None


def test_resolve_ignores_query_and_hash(build: Path) -> None:
    found = hud.resolve("/assets/app.js?v=2#top")
    assert found is not None
    assert found[0].name == "app.js"


def test_missing_file_is_none(build: Path) -> None:
    assert hud.resolve("/assets/nada.js") is None


def test_legacy_html_is_used_without_a_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = tmp_path / "index.html"
    legacy.write_text("<title>Nox legado</title>", encoding="utf-8")
    monkeypatch.delenv("NOX_UI_DIST", raising=False)
    monkeypatch.setattr(hud, "dist_dir", lambda: None)
    monkeypatch.setattr(hud, "LEGACY", legacy)

    assert hud.index_file() == legacy
    found = hud.resolve("/")
    assert found is not None
    assert found[0] == legacy


def test_no_hud_at_all_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hud, "dist_dir", lambda: None)
    monkeypatch.setattr(hud, "LEGACY", tmp_path / "ausente.html")
    with pytest.raises(FileNotFoundError):
        hud.index_file()
