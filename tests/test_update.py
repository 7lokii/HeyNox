"""Auto-atualização: manifesto, versões, sha256 e o script que troca a pasta."""

from __future__ import annotations

import hashlib
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from nox.ui import update as updater
from nox.ui.update import check, fetch_manifest


def make_zip(path: Path, *, exe: str = "HeyNox/HeyNox.exe") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(exe, b"binario")
        archive.writestr("HeyNox/_internal/config.yaml", b"nox:\n  name: Nox\n")
    data = buffer.getvalue()
    path.write_bytes(data)
    return data


class ArtefactServer:
    """Serve o manifesto e o zip numa porta local."""

    def __init__(self, manifest: dict, artefact: bytes | None = None, status: int = 200) -> None:
        self.manifest = manifest
        self.artefact = artefact or b""
        self.status = status
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):  # noqa: N802
                if self.path.endswith(".json"):
                    body = json.dumps(outer.manifest).encode()
                else:
                    body = outer.artefact
                self.send_response(outer.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/latest.json"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def test_version_tuple_and_comparison() -> None:
    assert updater.version_tuple("0.0.10") == (0, 0, 10)
    assert updater.version_tuple("1.2") == (1, 2)
    assert updater.version_tuple("") == (0,)
    assert updater.is_newer("0.0.2", "0.0.1") is True
    assert updater.is_newer("0.0.1", "0.0.1") is False
    assert updater.is_newer("0.0.10", "0.0.9") is True


def test_platform_key_is_one_of_the_manifest_keys() -> None:
    assert updater.platform_key() in {
        "windows-x64",
        "windows-arm64",
        "macos-arm64",
        "macos-x64",
        "linux-x64",
    }


def test_check_finds_a_newer_version() -> None:
    key = updater.platform_key()
    manifest = {
        "version": "9.9.9",
        "platforms": {key: {"portable": "9.9.9/HeyNox-9.9.9.zip"}},
        "sha256": {"HeyNox-9.9.9.zip": "a" * 64},
    }
    server = ArtefactServer(manifest)
    try:
        result = updater.check(server.url)
    finally:
        server.close()

    assert result["ok"] is True
    assert result["available"] is True
    assert result["latest"] == "9.9.9"
    assert result["release"]["url"].endswith("9.9.9/HeyNox-9.9.9.zip")
    assert result["release"]["url"].startswith("http://127.0.0.1")


def test_check_ignores_the_same_version() -> None:
    key = updater.platform_key()
    manifest = {
        "version": updater.__version__,
        "platforms": {key: {"portable": "x.zip"}},
        "sha256": {"x.zip": "a" * 64},
    }
    server = ArtefactServer(manifest)
    try:
        result = updater.check(server.url)
    finally:
        server.close()

    assert result["available"] is False


def test_check_refuses_a_manifest_without_checksum() -> None:
    key = updater.platform_key()
    manifest = {"version": "9.9.9", "platforms": {key: {"portable": "y.zip"}}}
    server = ArtefactServer(manifest)
    try:
        result = updater.check(server.url)
    finally:
        server.close()

    assert result["available"] is False
    assert "sha256" in result["error"]


def test_check_survives_an_unreachable_server() -> None:
    result = updater.check("http://127.0.0.1:9/latest.json")

    assert result["ok"] is False
    assert result["error"]


def test_check_rejects_a_non_http_url() -> None:
    with pytest.raises(ValueError):
        updater.fetch_manifest("file:///etc/passwd")


def test_download_and_stage_prepare_the_new_folder(tmp_path) -> None:
    payload = make_zip(tmp_path / "origem.zip")
    digest = hashlib.sha256(payload).hexdigest()
    release = updater.Release(version="9.9.9", url="http://127.0.0.1:9/x.zip", sha256=digest)

    server = ArtefactServer({}, artefact=payload)
    try:
        release = updater.Release(
            version="9.9.9",
            url=f"http://127.0.0.1:{server.server.server_address[1]}/HeyNox.zip",
            sha256=digest,
        )
        archive = updater.download(release, tmp_path / "update" / "HeyNox.zip")
    finally:
        server.close()

    assert archive.is_file()
    staged = updater.stage(archive, tmp_path / "update")
    assert (staged / "HeyNox.exe").is_file()
    assert (staged / "_internal" / "config.yaml").is_file()


def test_download_refuses_a_wrong_checksum(tmp_path) -> None:
    payload = make_zip(tmp_path / "origem.zip")
    server = ArtefactServer({}, artefact=payload)
    try:
        release = updater.Release(
            version="9.9.9",
            url=f"http://127.0.0.1:{server.server.server_address[1]}/HeyNox.zip",
            sha256="b" * 64,
        )
        with pytest.raises(ValueError, match="sha256"):
            updater.download(release, tmp_path / "update" / "HeyNox.zip")
    finally:
        server.close()

    assert not (tmp_path / "update" / "HeyNox.zip").exists()
    assert not (tmp_path / "update" / "HeyNox.zip.part").exists()


def test_apply_writes_a_script_that_mirrors_and_restarts(tmp_path) -> None:
    payload = make_zip(tmp_path / "origem.zip", exe="HeyNox/HeyNox.exe")
    digest = hashlib.sha256(payload).hexdigest()
    server = ArtefactServer({}, artefact=payload)
    target = tmp_path / "instalada"
    target.mkdir()
    try:
        release = updater.Release(
            version="9.9.9",
            url=f"http://127.0.0.1:{server.server.server_address[1]}/HeyNox.zip",
            sha256=digest,
        )
        script = updater.apply(release, target=target, workdir=tmp_path / "update")
    finally:
        server.close()

    text = script.read_text(encoding="utf-8")
    assert script.name == "apply.cmd"
    assert "robocopy" in text.lower()
    assert str(target) in text
    assert "HeyNox.exe" in text


def test_can_apply_needs_a_writable_folder(tmp_path) -> None:
    assert updater.writable(tmp_path) is True
    if updater.sys.platform.startswith("win"):
        assert updater.can_apply(tmp_path) is True


def test_manifesto_com_bom_do_powershell_e_lido() -> None:
    """`Set-Content -Encoding utf8` no PowerShell 5.1 escreve BOM e o json recusa."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    body = json.dumps(
        {
            "version": "0.0.2",
            "platforms": {"windows-x64": {"portable": "HeyNox-0.0.2.zip"}},
            "sha256": {"HeyNox-0.0.2.zip": "a" * 64},
        }
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b"\xef\xbb\xbf" + body)

        def log_message(self, *args) -> None:
            return

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        manifest = fetch_manifest(f"http://127.0.0.1:{httpd.server_port}/latest.json")
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert manifest["version"] == "0.0.2"


def test_caminho_relativo_no_manifesto_resolve_contra_o_manifesto() -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    body = json.dumps(
        {
            "version": "0.0.2",
            "platforms": {"windows-x64": {"portable": "0.0.2/HeyNox-0.0.2.zip"}},
            "sha256": {"HeyNox-0.0.2.zip": "b" * 64},
        }
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            return

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        result = check(f"http://127.0.0.1:{httpd.server_port}/latest.json")
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert result["ok"] is True
    assert result["release"]["url"].endswith("/0.0.2/HeyNox-0.0.2.zip")
