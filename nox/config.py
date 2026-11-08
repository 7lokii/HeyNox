"""Carregamento e validação da configuração do Nox."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class NoxError(Exception):
    """Erro de configuração ou de arranque do Nox."""


class ConfigError(NoxError):
    """O config.yaml é inválido ou não pode ser lido."""


class NoxIdentity(BaseModel):
    name: str = "Nox"
    language: str = "pt-PT"
    persona: str = "calm, direct, helpful, futuristic"
    wake_word: str = "hey nox"
    wake_word_sensitivity: float = Field(default=0.7, ge=0.0, le=1.0)
    voice_enabled: bool = True
    text_enabled: bool = True


class VadConfig(BaseModel):
    provider: Literal["silero", "webrtc"] = "silero"
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)


class AudioConfig(BaseModel):
    input_device: str = "default"
    sample_rate: int = Field(default=16000, gt=0)
    channels: int = Field(default=1, gt=0, le=2)
    vad: VadConfig = Field(default_factory=VadConfig)


class SttConfig(BaseModel):
    provider: Literal["faster-whisper", "openai"] = "faster-whisper"
    model: Literal["tiny", "base", "small", "medium", "large-v3"] = "small"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    language: str = "pt"
    fallback_provider: Literal["openai"] | None = "openai"


class LlmRouterConfig(BaseModel):
    simple_tasks: str = "groq"
    coding_tasks: str = "anthropic"
    private_tasks: str = "ollama"
    fallback: str = "openai_compatible"


class LlmConfig(BaseModel):
    default_provider: str = "openai_compatible"
    router: LlmRouterConfig = Field(default_factory=LlmRouterConfig)


class TtsConfig(BaseModel):
    provider: Literal["kokoro", "piper", "elevenlabs", "openai"] = "kokoro"
    voice: str = "pt-PT-male"
    speed: float = Field(default=1.0, gt=0.0, le=3.0)


class MemoryConfig(BaseModel):
    sqlite_path: Path = Path("data/nox.db")
    vector_store: Literal["chroma", "qdrant", "lancedb", "none"] = "chroma"
    embedding_provider: str = "local"


class GithubConfig(BaseModel):
    default_repo: str = "7lokii/HeyNox"
    default_branch: str = "main"
    allow_push_to_main: bool = False
    require_pr: bool = True
    require_tests: bool = True


ConfirmationAction = Literal[
    "delete",
    "force_push",
    "install",
    "system_change",
    "send_email",
    "purchase",
    "desktop_control",
]


class SecurityConfig(BaseModel):
    allowed_paths: list[Path] = Field(default_factory=lambda: [Path("./projects"), Path("./data")])
    blocked_paths: list[str] = Field(default_factory=lambda: [".env", ".git", "credentials"])
    allowed_commands: list[str] = Field(default_factory=list)
    require_confirmation: list[ConfirmationAction] = Field(default_factory=list)


class Config(BaseModel):
    nox: NoxIdentity = Field(default_factory=NoxIdentity)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    stt: SttConfig = Field(default_factory=SttConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    github: GithubConfig = Field(default_factory=GithubConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    @field_validator("nox", mode="after")
    @classmethod
    def _wake_word_not_empty(cls, value: NoxIdentity) -> NoxIdentity:
        if not value.wake_word.strip():
            raise ValueError("nox.wake_word não pode estar vazio")
        return value


def load_config(path: Path | str | None = None) -> Config:
    """Lê o config.yaml (ou o caminho indicado) e devolve uma Config validada."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"Ficheiro de configuração não encontrado: {config_path}") from exc
    except OSError as exc:
        raise ConfigError(f"Não foi possível ler {config_path}: {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML inválido em {config_path}: {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"O topo de {config_path} deve ser um mapa YAML")

    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Configuração inválida em {config_path}:\n{exc}") from exc


def load_environment(env_file: Path | str | None = None) -> None:
    """Carrega o .env sem o versionar. Variáveis já definidas no ambiente têm prioridade."""
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)


def data_dir() -> Path:
    """Diretório de dados, resolvido a partir de NOX_DATA_DIR."""
    with suppress(Exception):
        load_environment()
    path = Path(os.environ.get("NOX_DATA_DIR", "./data"))
    return path if path.is_absolute() else PROJECT_ROOT / path
