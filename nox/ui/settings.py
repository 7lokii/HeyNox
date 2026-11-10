"""Definições da interface: ler e escrever a configuração dentro da app.

A regra que isto serve: quem instala o Nox não edita ficheiros à mão. As
chaves ficam no `.env` do diretório de dados do utilizador e o resto num
`config.yaml` ao lado, copiado do original para não perder secções quando só
se muda uma linha.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nox.config import DEFAULT_CONFIG_PATH, load_config, load_environment, resolve_config_path
from nox.paths import user_data_dir

# Sem estas, o Nox responde só ao que é local.
MODEL_KEY = "NOX_LLM_API_KEY"
CLOUD_STT_KEY = "GROQ_API_KEY"
SECRETS = (MODEL_KEY, CLOUD_STT_KEY)


@dataclass(frozen=True)
class Provider:
    """Um fornecedor de modelo, para o ecrã de configuração não pedir URLs."""

    id: str
    label: str
    base_url: str
    api_format: str
    model: str
    key_env: str = MODEL_KEY
    needs_key: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "base_url": self.base_url,
            "api_format": self.api_format,
            "model": self.model,
            "key_env": self.key_env,
            "needs_key": self.needs_key,
        }


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "selora", "Selora (o atual)", "https://api.selora.lol/v1", "anthropic", "claude-haiku-5-5"
    ),
    Provider(
        "anthropic", "Anthropic", "https://api.anthropic.com/v1", "anthropic", "claude-haiku-latest"
    ),
    Provider("openai", "OpenAI", "https://api.openai.com/v1", "openai", "gpt-4o-mini"),
    Provider(
        "openrouter",
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "openai",
        "anthropic/claude-3.5-haiku",
    ),
    Provider("groq", "Groq", "https://api.groq.com/openai/v1", "openai", "llama-3.3-70b-versatile"),
    Provider(
        "ollama",
        "Ollama (local)",
        "http://127.0.0.1:11434/v1",
        "openai",
        "llama3.1",
        needs_key=False,
    ),
)


def provider_by_id(identifier: str) -> Provider | None:
    for provider in PROVIDERS:
        if provider.id == identifier:
            return provider
    return None


def provider_for(base_url: str, api_format: str) -> str:
    """Descobre o preset que corresponde à configuração em uso."""
    target = _normalize_url(base_url)
    for provider in PROVIDERS:
        if _normalize_url(provider.base_url) == target and provider.api_format == api_format:
            return provider.id
    return "custom"


def _normalize_url(value: str) -> str:
    """`localhost` e `127.0.0.1` são a mesma máquina; sem isto o preset não casava."""
    return value.strip().rstrip("/").replace("//localhost", "//127.0.0.1").lower()


def mask(value: str) -> str:
    """Devolve só o suficiente para reconhecer a chave, nunca a chave."""
    clean = value.strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "..." + clean[-2:]
    return "..." + clean[-4:]


class SettingsStore:
    """Lê e escreve as definições que o utilizador controla na interface."""

    def __init__(self, root: Path | None = None, config_path: Path | None = None) -> None:
        self.root = Path(root) if root is not None else user_data_dir()
        self.env_path = self.root / ".env"
        self.config_path = self.root / "config.yaml"
        self.config_source = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH

    # ---------------------------- leitura ----------------------------

    def read_env(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self.env_path.is_file():
            return values
        for raw in self.env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
        return values

    def secrets_status(self) -> dict[str, dict[str, Any]]:
        """Estado de cada chave: se existe e um rabo mascarado. Nunca o valor."""
        from_env = self.read_env()
        status: dict[str, dict[str, Any]] = {}
        for name in SECRETS:
            value = from_env.get(name) or os.environ.get(name, "")
            status[name] = {"set": bool(value.strip()), "preview": mask(value)}
        return status

    def source_path(self) -> Path:
        """O `config.yaml` que serve de base, exista ele onde existir.

        No pacote, `install_dir()/config.yaml` não existe: o ficheiro viaja em
        `_internal`. Pedir um caminho que não existe rebentava o pedido HTTP.
        """
        for candidate in (self.config_path, self.config_source):
            if candidate.is_file():
                return candidate
        return resolve_config_path(None)

    def effective_config(self):
        """A config que o Nox está mesmo a usar, com o utilizador à frente."""
        return load_config(self.source_path())

    def values(self) -> dict[str, Any]:
        config = self.effective_config()
        return {
            "name": config.nox.name,
            "wake_word": config.nox.wake_word,
            "voice_enabled": config.nox.voice_enabled,
            "provider": provider_for(config.llm.base_url, config.llm.api_format),
            "api_format": config.llm.api_format,
            "base_url": config.llm.base_url,
            "model": config.llm.model,
            "key_env": config.llm.api_key_env,
            "input_device": config.audio.input_device,
            "input_fallback": config.audio.input_fallback,
            "full_access": config.tools.full_access,
            "update_enabled": config.update.enabled,
            "update_manifest_url": config.update.manifest_url,
            "update_check_hours": config.update.check_hours,
        }

    def has_model_key(self) -> bool:
        """Se há chave para o fornecedor configurado, ou se ele não precisa."""
        config = self.effective_config()
        if not self._needs_key(config.llm.base_url, config.llm.api_format):
            return True
        if not config.llm.api_key_env.strip():
            return True
        name = config.llm.api_key_env
        value = self.read_env().get(name) or os.environ.get(name, "")
        return bool(value.strip())

    @staticmethod
    def _needs_key(base_url: str, api_format: str) -> bool:
        provider = provider_by_id(provider_for(base_url, api_format))
        return provider is None or provider.needs_key

    # --------------------------- escrita ----------------------------

    def _base_document(self) -> dict[str, Any]:
        """Parte do config.yaml em uso, para não perder o que não se mostra."""
        source = self.source_path()
        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{source} não tem um mapa YAML no topo")
        return raw

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Grava `.env` e `config.yaml` em dados do utilizador. Devolve o estado novo."""
        secrets_written = {"api_key": None, "groq_key": None}
        env = self.read_env()

        api_key = str(payload.get("api_key", "")).strip()
        if api_key:
            env[MODEL_KEY] = api_key
            secrets_written["api_key"] = mask(api_key)
        groq = str(payload.get("groq_key", "")).strip()
        if groq:
            env[CLOUD_STT_KEY] = groq
            secrets_written["groq_key"] = mask(groq)
        for name, flag in ((MODEL_KEY, "clear_api_key"), (CLOUD_STT_KEY, "clear_groq_key")):
            if payload.get(flag):
                env.pop(name, None)
                secrets_written["api_key" if name == MODEL_KEY else "groq_key"] = ""
        self._write_env(env)

        document = self._base_document()
        nox_section = document.setdefault("nox", {})
        if payload.get("name"):
            nox_section["name"] = str(payload["name"]).strip()
        if payload.get("wake_word"):
            nox_section["wake_word"] = str(payload["wake_word"]).strip()
        if "voice_enabled" in payload:
            nox_section["voice_enabled"] = bool(payload["voice_enabled"])

        audio_section = document.setdefault("audio", {})
        device = str(payload.get("input_device", "")).strip()
        if device:
            audio_section["input_device"] = device
        if payload.get("input_fallback"):
            audio_section["input_fallback"] = str(payload["input_fallback"]).strip()

        provider_id = str(payload.get("provider", "")).strip()
        provider = provider_by_id(provider_id)
        base_url = str(payload.get("base_url", "")).strip()
        api_format = str(payload.get("api_format", "")).strip()
        model = str(payload.get("model", "")).strip()
        if provider is not None:
            base_url = base_url or provider.base_url
            api_format = api_format or provider.api_format
            model = model or provider.model
        llm_section = document.setdefault("llm", {})
        if base_url:
            llm_section["base_url"] = base_url
        if api_format in ("anthropic", "openai"):
            llm_section["api_format"] = api_format
        if model:
            llm_section["model"] = model
        if provider is not None:
            llm_section["default_provider"] = provider.id
            # Um fornecedor local não tem chave: deixar o `api_key_env` apontado
            # fazia o `build_llm` exigir uma chave que não existe.
            llm_section["api_key_env"] = provider.key_env if provider.needs_key else ""

        if "full_access" in payload:
            document.setdefault("tools", {})["full_access"] = bool(payload["full_access"])

        update_section = document.setdefault("update", {})
        if "update_enabled" in payload:
            update_section["enabled"] = bool(payload["update_enabled"])
        if payload.get("update_manifest_url"):
            update_section["manifest_url"] = str(payload["update_manifest_url"]).strip()
        if payload.get("update_check_hours"):
            with suppress(TypeError, ValueError):
                update_section["check_hours"] = float(payload["update_check_hours"])

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        header = "# Escrito pela interface do Nox. Podes editar, mas a app volta a gravar.\n"
        self.config_path.write_text(
            header + yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        # A app tem de passar a usar isto agora, não no próximo arranque.
        load_environment(self.env_path)
        for name in SECRETS:
            value = env.get(name)
            if value:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)
        return {
            "values": self.values(),
            "secrets": self.secrets_status(),
            "written": secrets_written,
        }

    def _write_env(self, env: dict[str, str]) -> None:
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Chaves do Nox. Ficam só nesta máquina.", ""]
        for name in SECRETS:
            value = env.get(name, "").strip()
            if value:
                lines.append(f"{name}={value}")
        for name, value in env.items():
            if name not in SECRETS and value.strip():
                lines.append(f"{name}={value}")
        self.env_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")

    # ------------------------- teste de chave -------------------------

    def test_key(self, payload: dict[str, Any]) -> tuple[bool, str]:
        """Faz um pedido mínimo ao fornecedor para saber se a chave serve."""
        base_url = str(payload.get("base_url", "")).strip().rstrip("/")
        api_format = str(payload.get("api_format", "")).strip() or "openai"
        model = str(payload.get("model", "")).strip()
        key = str(payload.get("api_key", "")).strip()
        provider_id = str(payload.get("provider", "")).strip()

        provider = provider_by_id(provider_id)
        if provider is not None and not base_url:
            base_url = provider.base_url
        if provider is not None and not model:
            model = provider.model
        if not base_url.startswith(("http://", "https://")):
            return False, "O endereço tem de começar por http:// ou https://."
        if not key:
            key = self.read_env().get(MODEL_KEY) or os.environ.get(MODEL_KEY, "")
        if not key and (provider is None or provider.needs_key):
            return False, "Falta a chave."

        if api_format == "anthropic":
            url = f"{base_url}/messages"
            headers = {
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            }
            body = {
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "oi"}],
            }
        else:
            url = f"{base_url}/chat/completions"
            headers = {"content-type": "application/json", "authorization": f"Bearer {key}"}
            body = {
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "oi"}],
            }

        request = _request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
        try:
            # Só http(s): o endereço já foi validado acima.
            with _open(request, 25) as response:
                response.read(400)
        except urllib.error.HTTPError as exc:
            detail = exc.read(200).decode("utf-8", errors="replace")
            return False, f"O fornecedor respondeu {exc.code}. {_short(detail)}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return False, f"Não consegui chegar ao fornecedor: {_short(str(exc))}"
        return True, f"Chave aceite para {model}."


def _request(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None):
    """O único `Request` deste módulo, para o noqa ficar num sítio só."""
    return urllib.request.Request(  # noqa: S310 — só http(s)
        url, data=data, headers=headers or {}, method="POST"
    )


def _open(request: Any, timeout: float):
    """O único `urlopen` deste módulo, para o noqa ficar num sítio só."""
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 — só http(s)


def _short(text: str, limit: int = 160) -> str:
    clean = " ".join(str(text).split())
    return clean[:limit] + ("..." if len(clean) > limit else "")
