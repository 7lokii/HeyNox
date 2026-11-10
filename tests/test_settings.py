"""Definições dentro da app: chaves mascaradas, config escrita, teste de chave."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml

from nox.ui.settings import (
    MODEL_KEY,
    PROVIDERS,
    SettingsStore,
    mask,
    provider_by_id,
    provider_for,
)


@pytest.fixture(autouse=True)
def _sem_chaves_no_ambiente():
    """`save` escreve em os.environ; sem isto uma chave vazava para o teste seguinte."""
    names = ("NOX_LLM_API_KEY", "GROQ_API_KEY")
    for name in names:
        os.environ.pop(name, None)
    yield
    for name in names:
        os.environ.pop(name, None)


@pytest.fixture
def store(tmp_path) -> SettingsStore:
    return SettingsStore(root=tmp_path / "app")


def test_mask_shows_only_the_tail() -> None:
    assert mask("sk-abcdef123456") == "...3456"
    assert mask("curta") == "...ta"
    assert mask("") == ""


def test_store_starts_without_key_and_needs_setup(store) -> None:
    assert store.secrets_status()[MODEL_KEY]["set"] is False
    assert store.has_model_key() is False


def test_save_writes_env_and_config_inside_the_app_dir(store, tmp_path) -> None:
    result = store.save({"api_key": "chave-de-teste-9999", "name": "Nox", "wake_word": "hey nox"})

    assert store.env_path.is_file()
    assert store.config_path.is_file()
    assert f"{MODEL_KEY}=chave-de-teste-9999" in store.env_path.read_text(encoding="utf-8")
    assert result["written"]["api_key"] == "...9999"
    assert store.has_model_key() is True
    assert str(tmp_path) in str(store.env_path)


def test_the_key_never_comes_back_from_status(store) -> None:
    store.save({"api_key": "chave-secreta-abc123"})

    payload = json.dumps({"secrets": store.secrets_status()})

    assert "chave-secreta-abc123" not in payload
    assert store.secrets_status()[MODEL_KEY]["preview"] == "...c123"


def test_save_keeps_the_sections_it_does_not_show(store) -> None:
    store.save({"name": "Nox2"})

    document = yaml.safe_load(store.config_path.read_text(encoding="utf-8"))

    assert document["nox"]["name"] == "Nox2"
    # O que o ecrã não mostra tem de sobreviver: rotinas, memória, github.
    for section in ("memory", "github", "automation", "wake", "stt", "tts"):
        assert section in document


def test_save_applies_the_provider_preset(store) -> None:
    store.save({"provider": "openai"})

    values = store.values()

    assert values["base_url"] == "https://api.openai.com/v1"
    assert values["api_format"] == "openai"
    assert values["model"] == "gpt-4o-mini"


def test_save_writes_the_full_access_switch(store) -> None:
    store.save({"full_access": True})

    assert store.values()["full_access"] is True
    document = yaml.safe_load(store.config_path.read_text(encoding="utf-8"))
    assert document["tools"]["full_access"] is True


def test_save_writes_the_update_settings(store) -> None:
    store.save({"update_manifest_url": "https://exemplo.pt/latest.json", "update_check_hours": 3})

    values = store.values()

    assert values["update_manifest_url"] == "https://exemplo.pt/latest.json"
    assert values["update_check_hours"] == 3.0


def test_clearing_the_key_removes_it(store) -> None:
    store.save({"api_key": "chave-para-apagar"})
    store.save({"clear_api_key": True})

    assert store.has_model_key() is False
    assert "chave-para-apagar" not in store.env_path.read_text(encoding="utf-8")


def test_ollama_does_not_need_a_key(store) -> None:
    store.save({"provider": "ollama"})

    assert store.has_model_key() is True


def test_every_preset_has_an_http_endpoint() -> None:
    for provider in PROVIDERS:
        assert provider.base_url.startswith("http")
        assert provider.api_format in ("anthropic", "openai")


def test_current_setup_is_recognised_as_selora() -> None:
    assert provider_for("https://api.selora.lol/v1", "anthropic") == "selora"
    assert provider_by_id("selora") is not None


def test_test_key_refuses_a_bad_url(store) -> None:
    ok, message = store.test_key({"base_url": "ftp://x", "api_key": "k"})

    assert ok is False
    assert "http" in message


def test_test_key_refuses_without_key(store, monkeypatch) -> None:
    monkeypatch.delenv(MODEL_KEY, raising=False)

    ok, message = store.test_key({"provider": "openai", "base_url": "https://api.openai.com/v1"})

    assert ok is False
    assert "chave" in message.lower()


def _serve(status: int, body: bytes) -> tuple[str, ThreadingHTTPServer]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D102, ANN002
            return

        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/v1", server


def test_test_key_accepts_a_200(store) -> None:
    base, server = _serve(200, b'{"id": "ok"}')
    try:
        ok, message = store.test_key(
            {"base_url": base, "api_format": "openai", "model": "x", "api_key": "k"}
        )
    finally:
        server.shutdown()
        server.server_close()

    assert ok is True
    assert "aceite" in message.lower()


def test_test_key_reports_a_401(store) -> None:
    base, server = _serve(401, b'{"error": "chave invalida"}')
    try:
        ok, message = store.test_key(
            {"base_url": base, "api_format": "openai", "model": "x", "api_key": "k"}
        )
    finally:
        server.shutdown()
        server.server_close()

    assert ok is False
    assert "401" in message


def test_test_key_sends_the_anthropic_headers(store) -> None:
    seen: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):  # noqa: N802
            seen.update({key.lower(): value for key, value in self.headers.items()})
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        store.test_key({"base_url": base, "api_format": "anthropic", "model": "m", "api_key": "k"})
    finally:
        server.shutdown()
        server.server_close()

    assert seen.get("x-api-key") == "k"
    assert seen.get("anthropic-version")
