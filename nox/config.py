"""Carregamento e validação da configuração do Nox."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from nox.paths import bundle_dir, install_dir, user_data_dir

PROJECT_ROOT = install_dir()
DEFAULT_CONFIG_PATH = install_dir() / "config.yaml"


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
    # Frases curtas ("Hmm.") que cobrem o silêncio enquanto o Nox pensa.
    voice_fillers: bool = True


class VadConfig(BaseModel):
    provider: Literal["silero", "webrtc"] = "webrtc"
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    # 0 = permissivo, 3 = só aceita fala clara. 2 é o equilíbrio habitual.
    aggressiveness: int = Field(default=2, ge=0, le=3)
    # Silêncio que fecha a frase. Baixo demais corta quem respira a meio.
    silence_ms: int = Field(default=500, ge=200, le=2000)


class AudioConfig(BaseModel):
    # Nome (ou parte) do microfone preferido: se estiver ligado, é este que o
    # Nox usa. Um headset Bluetooth só aparece no sistema quando está ligado.
    input_device: str = "default"
    input_fallback: str = "default"
    sample_rate: int = Field(default=16000, gt=0)
    channels: int = Field(default=1, gt=0, le=2)
    # Energia mínima para sequer tentar transcrever. Abaixo disto é ruído.
    min_speech_rms: float = Field(default=120.0, gt=0)
    # Bloco de leitura. O WebRTC VAD só aceita 10, 20 ou 30 ms.
    block_ms: int = Field(default=30, gt=0)
    # Portão adaptativo antes da wake word: fecha o que não se distingue do
    # ruído de fundo aprendido.
    noise_gate: bool = True
    noise_gate_factor: float = Field(default=2.5, gt=1.0, le=10.0)
    # Limpa o áudio antes do reconhecedor da wake word. Experimental: em ruído
    # alto ajuda a frase longa, mas estraga palavras curtas como "Nox".
    denoise_wake: bool = False
    # Interromper o Nox a falar. Só é fiável com auscultadores: com
    # altifalantes o microfone ouve o próprio Nox e ele cala-se sozinho.
    barge_in: bool = False
    barge_in_ms: int = Field(default=300, ge=100, le=1500)
    barge_in_threshold: float = Field(default=800.0, gt=0)
    vad: VadConfig = Field(default_factory=VadConfig)

    @model_validator(mode="after")
    def _webrtc_limits(self) -> AudioConfig:
        if self.vad.provider != "webrtc":
            return self
        if self.block_ms not in (10, 20, 30):
            raise ValueError("audio.block_ms tem de ser 10, 20 ou 30 com o VAD webrtc")
        if self.sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError("audio.sample_rate tem de ser 8000, 16000, 32000 ou 48000")
        return self


class SttConfig(BaseModel):
    provider: Literal["faster-whisper", "openai"] = "faster-whisper"
    model: Literal["tiny", "base", "small", "medium", "large-v3"] = "small"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    compute_type: Literal["int8", "int8_float16", "float16", "float32"] = "int8"
    # 3 é o ponto onde o modelo deixa de dizer "está ouvindo" (pt-BR) e passa a
    # dizer "está a ouvir" (pt-PT), sem o custo do beam 5.
    beam_size: int = Field(default=3, ge=1, le=5)
    language: str = "pt"
    # Texto de arranque que enviesa o descodificador. Vazio = gerado a partir do
    # nome e da wake word, para o modelo não trocar "Nox" por "nosso".
    initial_prompt: str = ""
    # STT na cloud (provider "openai"): mais rápido e preciso, mas o áudio sai
    # do PC. Compatível com Groq e OpenAI.
    cloud_base_url: str = "https://api.groq.com/openai/v1"
    cloud_model: str = "whisper-large-v3-turbo"
    cloud_api_key_env: str = "GROQ_API_KEY"
    timeout: float = Field(default=30.0, gt=0)
    # Corta o silêncio das pontas antes de transcrever: menos áudio, menos tempo.
    trim_silence: bool = True
    # Subtração espectral antes de transcrever. Ajuda em ruído forte; em
    # silêncio não muda nada.
    denoise: bool = True
    denoise_strength: float = Field(default=1.5, ge=0.0, le=4.0)
    fallback_provider: Literal["faster-whisper"] | None = "faster-whisper"


class LlmRouterConfig(BaseModel):
    simple_tasks: str = "groq"
    coding_tasks: str = "anthropic"
    private_tasks: str = "ollama"
    fallback: str = "openai_compatible"


class LlmConfig(BaseModel):
    """Onde e como o Nox fala com o modelo.

    `api_format` distingue os dois dialetos suportados: `anthropic` para
    `POST /messages` e `openai` para `POST /chat/completions`.
    """

    default_provider: str = "openai_compatible"
    model: str = ""
    api_format: Literal["anthropic", "openai"] = "openai"
    base_url: str = ""
    api_key_env: str = "NOX_LLM_API_KEY"
    # Alguns modelos gastam parte do orçamento num bloco de raciocínio
    # antes de escrever; 400 chegava para ficar sem resposta.
    max_tokens: int = Field(default=1200, gt=0)
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    timeout: float = Field(default=30.0, gt=0)
    router: LlmRouterConfig = Field(default_factory=LlmRouterConfig)


class TtsConfig(BaseModel):
    provider: Literal["piper", "edge", "kokoro", "elevenlabs", "openai"] = "piper"
    voice: str = "pt_PT-tugão-medium"
    speed: float = Field(default=1.0, gt=0.0, le=3.0)


class MemoryConfig(BaseModel):
    sqlite_path: Path = Path("data/nox.db")
    # O FTS5 do SQLite cobre a pesquisa por palavra; Chroma fica para quando a
    # pesquisa semântica justificar o peso das dependências.
    vector_store: Literal["chroma", "qdrant", "lancedb", "none"] = "none"
    embedding_provider: str = "local"
    enabled: bool = True
    history_turns: int = Field(default=12, ge=0, le=100)


class GithubConfig(BaseModel):
    default_repo: str = "7lokii/HeyNox"
    default_branch: str = "main"
    allow_push_to_main: bool = False
    require_pr: bool = True
    require_tests: bool = True


class McpServerConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class McpConfig(BaseModel):
    """Servidores MCP por stdio. Desligado por omissão: arrancar processos
    externos no arranque não pode ser surpresa."""

    enabled: bool = False
    timeout_s: float = Field(default=20.0, gt=0)
    servers: dict[str, McpServerConfig] = Field(default_factory=dict)


class AutomationConfig(BaseModel):
    """Rotinas que correm sozinhas enquanto a interface estiver aberta."""

    enabled: bool = True
    tick_s: float = Field(default=30.0, gt=0)


class DesktopConfig(BaseModel):
    """Controlo do PC. Desligado por omissão; cada ação pede aprovação."""

    enabled: bool = False
    confirm_actions: bool = True
    # Aplicações que o Nox pode abrir. Vazio = nenhuma.
    allowed_apps: list[str] = Field(default_factory=list)
    screenshot_dir: str = "data/screenshots"


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
    # Nem com aprovação: são destrutivos por natureza.
    blocked_commands: list[str] = Field(
        default_factory=lambda: [
            "rm -rf",
            "rm -r",
            "del /s",
            "del /q",
            "rd /s",
            "format",
            "diskpart",
            "mkfs",
            "shutdown",
            "reg delete",
            "cipher /w",
            "vssadmin",
            "dd if=",
        ]
    )
    require_confirmation: list[ConfirmationAction] = Field(default_factory=list)


class WakeConfig(BaseModel):
    """Ativação por voz. `off` deixa o Nox a ouvir sempre."""

    provider: Literal["vosk", "off"] = "vosk"
    model: str = "vosk-model-small-pt-0.3"
    # Qualquer uma destas formas ativa o Nox. Basta a palavra distintiva.
    phrases: list[str] = Field(default_factory=lambda: ["nox", "ei nox", "hey nox"])
    # Vocabulário restrito do reconhecedor. "nox" não existe no dicionário do
    # modelo pt (ele escreve "inox"); limitar as hipóteses faz com que até um
    # "Nox" curto seja ouvido, em vez de virar outra palavra qualquer.
    grammar: list[str] = Field(default_factory=lambda: ["inox", "ei inox", "[unk]"])
    # Só o dono do perfil de voz ativa o Nox. Requer `nox --enroll` primeiro.
    voiceprint: bool = True
    voiceprint_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    # Segundos à espera do pedido depois de ouvir a wake word.
    timeout_s: float = Field(default=8.0, gt=0)
    # Depois de responder, o Nox continua a ouvir sem exigir a palavra outra
    # vez — uma réplica não deve obrigar a dizer "Hey Nox" de novo.
    follow_up_s: float = Field(default=6.0, ge=0.0, le=60.0)


class ToolsConfig(BaseModel):
    enabled: bool = True
    # Quantas voltas de ferramentas antes de desistir.
    max_steps: int = Field(default=4, ge=1, le=10)
    command_timeout: float = Field(default=60.0, gt=0)
    # Quanto tempo a interface tem para aprovar uma ação antes de a recusar.
    approval_timeout_s: float = Field(default=45.0, gt=0)
    # Escrever ficheiros exige aprovação. Desligar só se confiares no modelo.
    confirm_writes: bool = True
    # Acesso total: nenhuma ferramenta pede aprovação. Ligado à mão no ecrã de
    # definições, com aviso. Tudo o que passa por aqui fica no audit.jsonl, e a
    # paragem de emergência continua a bloquear o controlo do PC.
    full_access: bool = False


class UpdateConfig(BaseModel):
    """Auto-atualização a partir do manifesto das releases."""

    enabled: bool = True
    check_hours: float = Field(default=6.0, gt=0)
    # Manifesto público. Sem rede ou 404, a app segue sem novidades.
    manifest_url: str = "https://raw.githubusercontent.com/7lokii/HeyNox/main/releases/latest.json"
    # Aplicar sozinho exige uma pasta gravável: só o portátil cumpre isto.
    allow_apply: bool = True


class Config(BaseModel):
    nox: NoxIdentity = Field(default_factory=NoxIdentity)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    wake: WakeConfig = Field(default_factory=WakeConfig)
    stt: SttConfig = Field(default_factory=SttConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    automation: AutomationConfig = Field(default_factory=AutomationConfig)
    desktop: DesktopConfig = Field(default_factory=DesktopConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    github: GithubConfig = Field(default_factory=GithubConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @field_validator("nox", mode="after")
    @classmethod
    def _wake_word_not_empty(cls, value: NoxIdentity) -> NoxIdentity:
        if not value.wake_word.strip():
            raise ValueError("nox.wake_word não pode estar vazio")
        return value


def load_config(path: Path | str | None = None) -> Config:
    """Lê o config.yaml (ou o caminho indicado) e devolve uma Config validada."""
    config_path = resolve_config_path(path)
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


def resolve_config_path(path: Path | str | None) -> Path:
    """Prefere um config.yaml editado em %LOCALAPPDATA%\\HeyNox ao embutido/instalado."""
    if path:
        return Path(path)
    user_config = user_data_dir() / "config.yaml"
    if user_config.is_file():
        return user_config
    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH
    return bundle_dir() / "config.yaml"


def load_environment(env_file: Path | str | None = None) -> None:
    """Carrega o .env sem o versionar. Variáveis já definidas no ambiente têm prioridade."""
    candidates = [env_file] if env_file else [user_data_dir() / ".env", PROJECT_ROOT / ".env"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            load_dotenv(candidate, override=False)


def data_dir() -> Path:
    """Diretório de dados, resolvido a partir de NOX_DATA_DIR."""
    with suppress(Exception):
        load_environment()
    path = Path(os.environ.get("NOX_DATA_DIR", "./data"))
    return path if path.is_absolute() else PROJECT_ROOT / path
