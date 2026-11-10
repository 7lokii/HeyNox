"""Encontrar e resolver os ficheiros do HUD que a janela mostra.

Duas gerações convivem:

- `ui/dist`, o HUD em TypeScript compilado pelo Vite. É o que a app desktop usa.
- `nox/ui/index.html`, o HUD original de ficheiro único. Fica como rede de
  segurança: sem `npm run build` a interface continua a abrir.

A ordem de procura é explícita para o pacote e o código-fonte se comportarem
da mesma maneira. `NOX_UI_DIST` existe para apontar a um build em curso.
"""

from __future__ import annotations

import os
from pathlib import Path

from nox.paths import bundle_dir

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
}

LEGACY = Path(__file__).with_name("index.html")


def dist_dir() -> Path | None:
    """Pasta do HUD compilado, ou None se ainda não houver build."""
    candidates: list[Path] = []
    override = os.environ.get("NOX_UI_DIST")
    if override:
        candidates.append(Path(override))
    candidates.append(Path(__file__).resolve().parent.parent.parent / "ui" / "dist")
    candidates.append(bundle_dir() / "ui" / "dist")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def index_file() -> Path:
    """O `index.html` a servir na raiz."""
    root = dist_dir()
    if root is not None:
        return root / "index.html"
    if LEGACY.is_file():
        return LEGACY
    raise FileNotFoundError("HUD não encontrado: nem ui/dist nem nox/ui/index.html")


def resolve(url_path: str) -> tuple[Path, str] | None:
    """Traduz um caminho de URL num ficheiro real, ou None.

    O HUD compilado vive em `ui/dist`, o legado ao lado deste módulo. Só se
    serve o que estiver dentro de uma destas raízes: um `..` no caminho não pode
    transformar o servidor local num leitor de disco.
    """
    clean = url_path.split("?", 1)[0].split("#", 1)[0]
    if not clean.startswith("/"):
        return None
    root = dist_dir()
    relative = clean.lstrip("/")
    if relative in ("", "index.html"):
        try:
            target = index_file()
        except FileNotFoundError:
            return None
        return target, MIME[".html"]

    roots: list[Path] = []
    if root is not None:
        roots.append(root)
    roots.append(LEGACY.parent)

    for base in roots:
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate, MIME.get(candidate.suffix.lower(), "application/octet-stream")
    return None
