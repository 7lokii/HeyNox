"""Ponto de entrada do HeyNox."""

from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from io import TextIOWrapper
from pathlib import Path
from typing import cast

from nox.config import Config, ConfigError, load_config
from nox.optional import available

VOICE_MODULES = ("sounddevice", "numpy", "openwakeword", "faster_whisper", "kokoro")


def _check(config: Config) -> list[str]:
    """Devolve a lista de avisos de arranque, sem falhar por falta de extras."""
    warnings: list[str] = []
    missing = [name for name in VOICE_MODULES if not available(name)]
    if missing and config.nox.voice_enabled:
        warnings.append(
            f"Modo voz ativo mas faltam dependências: {', '.join(missing)} "
            "(pip install -e .[voice])"
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
    return parser


def _fix_console_encoding() -> None:
    # A consola do Windows usa cp1252 por defeito e estraga acentos nos avisos.
    for stream in (sys.stdout, sys.stderr):
        with suppress(AttributeError, ValueError):
            cast("TextIOWrapper", stream).reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _fix_console_encoding()
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2

    warnings = _check(config)
    for warning in warnings:
        print(f"aviso: {warning}", file=sys.stderr)

    if args.check:
        wake_word = config.nox.wake_word
        print(f"{config.nox.name} configurado ({config.nox.language}), wake word '{wake_word}'")
        return 0

    print(f"{config.nox.name} 0.x — fundações instaladas. O pipeline de voz chega na Fase 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
