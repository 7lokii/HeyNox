"""Ponto de entrada do HeyNox."""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path
from typing import cast

from nox.audio.types import duration_ms
from nox.audio.wav import read_wav, write_wav
from nox.brain.agent import Agent
from nox.brain.llm import LlmError, UnconfiguredLlm, build_llm
from nox.config import (
    Config,
    ConfigError,
    NoxError,
    load_config,
    load_environment,
    resolve_config_path,
)
from nox.optional import available
from nox.paths import has_console, user_data_dir
from nox.speech.stt import build_transcriber
from nox.speech.tts import build_synthesizer

VOICE_MODULES = ("sounddevice", "numpy", "openwakeword", "faster_whisper", "piper")


def _check(config: Config) -> list[str]:
    """Devolve a lista de avisos de arranque, sem falhar por falta de extras."""
    warnings: list[str] = []
    missing = [name for name in VOICE_MODULES if not available(name)]
    if missing and config.nox.voice_enabled:
        warnings.append(
            f"Modo voz ativo mas faltam dependências: {', '.join(missing)} "
            "(pip install -e .[voice])"
        )
    if not os.environ.get(config.llm.api_key_env, "").strip():
        warnings.append(
            f"Sem chave de modelo ({config.llm.api_key_env}): só respostas locais "
            "até configurares o .env"
        )
    data_dir = config.memory.sqlite_path.parent
    if not data_dir.exists():
        warnings.append(f"Diretório de dados ainda não existe: {data_dir}")
    return warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nox", description="HeyNox — assistente pessoal Nox")
    parser.add_argument("--config", type=Path, default=None, help="Caminho para o config.yaml")
    parser.add_argument(
        "--check", action="store_true", help="Valida a configuração e o ambiente e sai"
    )
    parser.add_argument("--text", action="store_true", help="Conversa por texto, sem microfone")
    parser.add_argument("--say", metavar="FRASE", default=None, help="Responde a uma frase e sai")
    parser.add_argument(
        "--speak", metavar="TEXTO", default=None, help="Sintetiza a frase para WAV e sai"
    )
    parser.add_argument(
        "--transcribe", metavar="WAV", type=Path, default=None, help="Transcreve um WAV e sai"
    )
    parser.add_argument("--out", metavar="WAV", type=Path, default=None, help="Destino do --speak")
    return parser


def _fix_console_encoding() -> None:
    # A consola do Windows usa cp1252 por defeito e estraga acentos nos avisos.
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        with suppress(AttributeError, ValueError):
            cast("TextIOWrapper", stream).reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _fix_console_encoding()
    attached = has_console()
    sink = _emit if attached else _append_log
    try:
        return _run(build_parser().parse_args(argv), sink)
    except ConfigError as exc:
        sink(f"Erro de configuração: {exc}")
        return 2
    except Exception:
        if attached:
            raise
        _append_log(traceback.format_exc())
        return 1


def _run(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    load_environment()
    config = load_config(args.config)
    warnings = _check(config)
    for warning in warnings:
        out(f"aviso: {warning}")
    if args.check:
        wake_word = config.nox.wake_word
        out(f"{config.nox.name} configurado ({config.nox.language}), wake word '{wake_word}'")
        out(f"config: {resolve_config_path(args.config)}")
        return 0
    if args.say:
        return _reply_once(config, args.say, out)
    if args.speak:
        return _speak(config, args.speak, args.out, out)
    if args.transcribe:
        return _transcribe(config, args.transcribe, out)
    if args.text:
        return _text_session(config, out)
    out(f"{config.nox.name} pronto. Usa --text para conversar ou --check para diagnóstico.")
    return 0


def _speak(config: Config, text: str, destination: Path | None, out: Callable[[str], None]) -> int:
    try:
        synthesizer = build_synthesizer(config, progress=lambda message: out(f"aviso: {message}"))
        audio = synthesizer.synthesize(text)
    except NoxError as exc:
        out(f"Erro: {exc}")
        return 2
    if not audio:
        out("Erro: não foi gerado áudio")
        return 2

    target = destination or user_data_dir() / "out" / "nox.wav"
    try:
        write_wav(target, audio, synthesizer.sample_rate)
    except OSError as exc:
        out(f"Erro: não consegui escrever {target}: {exc}")
        return 2
    out(f"{duration_ms(audio, synthesizer.sample_rate)} ms -> {target}")
    return 0


def _transcribe(config: Config, path: Path, out: Callable[[str], None]) -> int:
    try:
        audio, sample_rate = read_wav(path)
        transcriber = build_transcriber(config)
        text = transcriber.transcribe(audio, sample_rate)
    except NoxError as exc:
        out(f"Erro: {exc}")
        return 2
    out(text or "(nada percetível)")
    return 0


def _agent(config: Config) -> Agent:
    """Constrói o agente; sem chave, degrada para respostas locais em vez de falhar."""
    try:
        llm = build_llm(config)
    except LlmError as exc:
        llm = UnconfiguredLlm(str(exc))
    return Agent(llm)


def _reply_once(config: Config, text: str, out: Callable[[str], None]) -> int:
    try:
        out(_agent(config).reply(text))
    except LlmError as exc:
        out(f"Erro: {exc}")
        return 2
    return 0


def _text_session(config: Config, out: Callable[[str], None]) -> int:
    if not has_console():
        out("Erro: o modo texto precisa de uma consola")
        return 2

    agent = _agent(config)
    out(f"{config.nox.name} em modo texto. Escreve 'sair' para terminar.")
    while True:
        try:
            line = input("tu> ")
        except (EOFError, KeyboardInterrupt):
            out("")
            return 0
        command = line.strip()
        if command.lower() in {"sair", "exit", "quit"}:
            return 0
        if not command:
            continue
        try:
            out(f"{config.nox.name}: {agent.reply(command)}")
        except LlmError as exc:
            out(f"Erro: {exc}")


def _emit(message: str) -> None:
    stream = sys.stderr if message.startswith(("aviso:", "Erro")) else sys.stdout
    if stream is not None:
        print(message, file=stream)


def log_path() -> Path:
    return user_data_dir() / "logs" / "nox.log"


def _append_log(message: str) -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {message.rstrip()}\n")


if __name__ == "__main__":
    raise SystemExit(main())
