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
from nox.brain.agent import build_agent
from nox.brain.llm import LlmError
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
from nox.voice import run_voice


def voice_modules(config: Config) -> list[str]:
    """Só as dependências que a configuração atual vai mesmo usar."""
    modules = ["sounddevice", "numpy"]
    if config.wake.provider == "vosk":
        modules.append("vosk")
    if config.stt.provider == "faster-whisper":
        modules.append("faster_whisper")
    if config.tts.provider == "piper":
        modules.append("piper")
    elif config.tts.provider == "edge":
        modules.append("edge_tts")
    if config.audio.vad.provider == "webrtc":
        modules.append("webrtcvad")
    return modules


def _check(config: Config) -> list[str]:
    """Devolve a lista de avisos de arranque, sem falhar por falta de extras."""
    warnings: list[str] = []
    missing = [name for name in voice_modules(config) if not available(name)]
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
    if config.wake.voiceprint:
        from nox.audio.voiceprint import load_profiles

        if not load_profiles():
            warnings.append(
                "wake.voiceprint ativo mas sem perfil de voz: qualquer voz ativa o Nox "
                "(corre 'nox --enroll')"
            )
    if config.desktop.enabled:
        missing_desktop = [
            name for name in ("pyautogui", "pygetwindow", "mss") if not available(name)
        ]
        if missing_desktop:
            warnings.append(
                f"Controlo do PC ativo mas faltam dependências: {', '.join(missing_desktop)} "
                "(pip install -e .[desktop])"
            )
        elif sys.platform == "win32" and not available("winrt.windows.media.ocr"):
            warnings.append("OCR indisponível: falta o winrt (pip install -e .[desktop])")
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
    parser.add_argument("--voice", action="store_true", help="Conversa por voz, com microfone")
    parser.add_argument(
        "--input", metavar="WAV", type=Path, default=None, help="Usa um WAV em vez do microfone"
    )
    parser.add_argument(
        "--no-wake", action="store_true", help="Ouve sempre, sem esperar pela palavra de ativação"
    )
    parser.add_argument(
        "--devices", action="store_true", help="Lista os microfones disponíveis e sai"
    )
    parser.add_argument("--ui", action="store_true", help="Abre a interface web local")
    parser.add_argument("--routines", action="store_true", help="Lista as rotinas e sai")
    parser.add_argument("--memory", action="store_true", help="Mostra o que o Nox sabe e sai")
    parser.add_argument(
        "--forget", metavar="TEXTO", default=None, help="Esquece os factos que contenham o texto"
    )
    parser.add_argument(
        "--memory-export", metavar="JSON", type=Path, default=None, help="Exporta a memória"
    )
    parser.add_argument(
        "--memory-import", metavar="JSON", type=Path, default=None, help="Importa a memória"
    )
    parser.add_argument(
        "--memory-reset", action="store_true", help="Apaga factos e histórico de conversa"
    )
    parser.add_argument(
        "--enroll", action="store_true", help="Grava 3 amostras da tua voz pelo microfone"
    )
    parser.add_argument(
        "--enroll-files",
        nargs="+",
        metavar="WAV",
        type=Path,
        default=None,
        help="Cria o perfil de voz a partir de ficheiros WAV",
    )
    parser.add_argument("--voiceprint", action="store_true", help="Mostra os perfis de voz")
    parser.add_argument(
        "--test-stt",
        nargs="?",
        const=4.0,
        type=float,
        metavar="SEGUNDOS",
        default=None,
        help="Grava do microfone e mostra o que o STT ouviu",
    )
    parser.add_argument(
        "--name", metavar="NOME", default=None, help="Nome do perfil a criar/apagar"
    )
    parser.add_argument("--forget-voice", action="store_true", help="Apaga o perfil de voz")
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
    if args.voice:
        return run_voice(config, out=out, input_file=args.input, use_wake=not args.no_wake)
    if args.devices:
        return _devices(config, out)
    if args.ui:
        from nox.ui.server import serve

        return serve(config, out=out)
    if args.enroll or args.enroll_files or args.voiceprint or args.forget_voice:
        return _voiceprint_command(config, args, out)
    if args.test_stt is not None:
        return _test_stt(config, args.test_stt, out)
    if args.routines:
        return _routines_command(out)
    if args.memory or args.forget or args.memory_export or args.memory_import or args.memory_reset:
        return _memory_command(config, args, out)
    if args.text:
        return _text_session(config, out)
    out(f"{config.nox.name} pronto. Usa --text para conversar ou --check para diagnóstico.")
    return 0


def _routines_command(out: Callable[[str], None]) -> int:
    from datetime import datetime

    from nox.automation.routines import RoutineStore

    routines = RoutineStore().load()
    if not routines:
        out("não há rotinas")
        return 0
    for routine in routines:
        state = "ativa" if routine.enabled else "desligada"
        last = (
            datetime.fromtimestamp(routine.last_run).strftime("%Y-%m-%d %H:%M")
            if routine.last_run
            else "nunca"
        )
        out(f"{routine.id} [{state}] {routine.schedule} (última: {last}) — {routine.prompt}")
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


def _memory_command(config: Config, args: argparse.Namespace, out: Callable[[str], None]) -> int:
    from nox.memory.store import MemoryStore, resolve_memory_path

    store = MemoryStore(resolve_memory_path(config))
    try:
        if args.memory_reset:
            facts = store.clear_facts()
            turns = store.clear_turns()
            out(f"apagados {facts} factos e {turns} turnos")
        if args.forget:
            removed = store.forget(args.forget)
            out(f"{removed} factos esquecidos" if removed else "não tinha nada sobre isso")
        if args.memory_import:
            turns, facts = store.load_from(args.memory_import)
            out(f"importados {turns} turnos e {facts} factos")
        if args.memory_export:
            path = store.save_to(args.memory_export)
            out(f"memória exportada para {path}")
        if args.memory:
            facts = store.facts(limit=50)
            out(f"memória: {resolve_memory_path(config)}")
            out(f"{len(facts)} factos, {store.count_turns()} turnos guardados")
            for fact in facts:
                out(f"  [{fact.kind}] {fact.text}")
    finally:
        store.close()
    return 0


def _voiceprint_command(
    config: Config, args: argparse.Namespace, out: Callable[[str], None]
) -> int:
    from nox.audio.voiceprint import (
        VoiceprintError,
        add_profile,
        build_profile,
        forget_profile,
        load_profiles,
        profile_path,
    )

    try:
        if args.forget_voice:
            removed = forget_profile(args.name)
            if not removed:
                out("não havia perfil guardado")
            elif args.name:
                out(f"perfil de {args.name} apagado")
            else:
                out(f"{removed} perfil(is) apagado(s)")

        if args.voiceprint:
            perfis = load_profiles()
            if not perfis:
                out(f"sem perfil de voz em {profile_path()} — usa --enroll")
            else:
                out(f"perfis: {profile_path()}")
                for perfil in perfis:
                    dimensoes = len(perfil.embedding)
                    out(f"  {perfil.name}: {perfil.samples} amostras, {dimensoes} dimensões")

        if args.enroll_files:
            from nox.audio.types import resample
            from nox.audio.wav import read_wav

            clips = []
            for path in args.enroll_files:
                audio, rate = read_wav(path)
                clips.append(resample(audio, rate, 16000))
            perfil = build_profile(clips, 16000)
            perfil.name = args.name or "eu"
            add_profile(perfil)
            out(f"perfil de {perfil.name} criado com {perfil.samples} amostras")

        if args.enroll:
            if not has_console():
                out("Erro: a inscrição precisa de uma consola")
                return 2
            from nox.audio.mic import SoundDeviceSource
            from nox.audio.types import Pcm

            source = SoundDeviceSource(
                sample_rate=config.audio.sample_rate, block_ms=config.audio.block_ms
            )
            frames = round(config.audio.sample_rate * config.audio.block_ms / 1000)
            blocos = round(2000 / config.audio.block_ms)
            clips = []
            try:
                for index in range(3):
                    input(f"amostra {index + 1}/3 — Enter e diz «Nox» ")
                    source.flush()
                    clips.append(Pcm(b"".join(source.read(frames) for _ in range(blocos))))
            finally:
                source.close()
            perfil = build_profile(clips, config.audio.sample_rate)
            perfil.name = args.name or "eu"
            add_profile(perfil)
            out(f"perfil de {perfil.name} criado com {perfil.samples} amostras")
    except (NoxError, VoiceprintError) as exc:
        out(f"Erro: {exc}")
        return 2
    return 0


def _test_stt(config: Config, seconds: float, out: Callable[[str], None]) -> int:
    """Grava alguns segundos e mostra o texto tal como o reconhecedor o ouviu."""
    if not has_console():
        out("Erro: o teste de STT precisa de uma consola")
        return 2

    from nox.audio.mic import SoundDeviceSource
    from nox.audio.types import Pcm

    try:
        source = SoundDeviceSource(
            sample_rate=config.audio.sample_rate, block_ms=config.audio.block_ms
        )
    except NoxError as exc:
        out(f"Erro: {exc}")
        return 2

    frames = round(config.audio.sample_rate * config.audio.block_ms / 1000)
    blocos = max(1, round(seconds * 1000 / config.audio.block_ms))
    try:
        input(f"Fala agora ({seconds:.0f} s) — Enter para começar ")
        source.flush()
        audio = Pcm(b"".join(source.read(frames) for _ in range(blocos)))
    finally:
        source.close()

    try:
        transcriber = build_transcriber(config)
        texto = transcriber.transcribe(audio, config.audio.sample_rate)
    except NoxError as exc:
        out(f"Erro: {exc}")
        return 2
    out(f"ouvi: {texto!r}" if texto else "ouvi: (nada)")
    return 0


def _devices(config: Config, out: Callable[[str], None]) -> int:
    from nox.audio.devices import input_devices, resolve_input

    try:
        devices = input_devices()
        chosen, label = resolve_input(config.audio.input_device, config.audio.input_fallback)
    except NoxError as exc:
        out(f"Erro: {exc}")
        return 2

    out(f"preferido: {config.audio.input_device!r} -> {label}")
    for index, name in devices:
        marca = "  <-" if index == chosen else ""
        out(f"{index:3}  {name}{marca}")
    return 0


def _reply_once(config: Config, text: str, out: Callable[[str], None]) -> int:
    try:
        out(build_agent(config).reply(text))
    except LlmError as exc:
        out(f"Erro: {exc}")
        return 2
    return 0


def _text_session(config: Config, out: Callable[[str], None]) -> int:
    if not has_console():
        out("Erro: o modo texto precisa de uma consola")
        return 2

    agent = build_agent(config)
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
