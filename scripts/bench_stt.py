"""Compara a transcrição local com a da cloud nas amostras de `data/`.

Uso:
    python scripts/bench_stt.py              # as duas
    python scripts/bench_stt.py --cloud      # só a cloud
    python scripts/bench_stt.py a.wav b.wav  # ficheiros à escolha
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from nox.audio.wav import read_wav
from nox.config import load_config, load_environment
from nox.models import ModelError
from nox.speech.stt import build_transcriber

DEFAULT_FILES = [
    "data/pergunta.wav",
    "data/pergunta2.wav",
    "data/duas-vezes.wav",
    "data/wake.wav",
]


def run(provider: str, files: list[Path]) -> None:
    load_environment()
    config = load_config()
    config.stt.provider = provider  # type: ignore[assignment]
    transcriber = build_transcriber(config)
    print(f"\n== {provider} ==")
    for path in files:
        audio, rate = read_wav(path)
        started = time.perf_counter()
        try:
            text = transcriber.transcribe(audio, rate)
        except ModelError as exc:
            print(f"{path.name:<18} ERRO  {exc}")
            continue
        elapsed = time.perf_counter() - started
        print(f"{path.name:<18} {elapsed:5.2f}s  {text!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--local", action="store_true", help="Só faster-whisper")
    parser.add_argument("--cloud", action="store_true", help="Só a API (Groq/OpenAI)")
    args = parser.parse_args()

    files = args.files or [Path(name) for name in DEFAULT_FILES]
    missing = [path for path in files if not path.exists()]
    if missing:
        raise SystemExit(f"não encontrei: {', '.join(str(p) for p in missing)}")

    both = not args.local and not args.cloud
    if both or args.local:
        run("faster-whisper", files)
    if both or args.cloud:
        run("openai", files)


if __name__ == "__main__":
    main()
