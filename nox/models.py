"""Modelos locais: onde vivem e como são descarregados.

O downloader do `piper-tts` não faz URL-encoding dos nomes de voz, por isso
`pt_PT-tugão-medium` rebenta com `UnicodeEncodeError`. Aqui o caminho é montado
segmento a segmento e citado como deve ser.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from nox.config import NoxError
from nox.paths import user_data_dir

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
SPEAKER_URL = (
    "https://huggingface.co/onnx-community/wespeaker-voxceleb-resnet34-LM"
    "/resolve/main/onnx/model.onnx"
)
VOSK_BASE = "https://alphacephei.com/vosk/models"

_VOICE_PATTERN = re.compile(
    r"^(?P<family>[^-]+)_(?P<region>[^-]+)-(?P<name>[^-]+)-(?P<quality>.+)$"
)


class ModelError(NoxError):
    """O modelo não existe, não pôde ser descarregado ou está corrompido."""


def piper_dir() -> Path:
    return user_data_dir() / "models" / "piper"


def vosk_dir() -> Path:
    return user_data_dir() / "models" / "vosk"


def speaker_dir() -> Path:
    return user_data_dir() / "models" / "wespeaker"


def voice_urls(voice: str) -> tuple[str, str]:
    """URLs do modelo e do JSON de configuração, já com o caminho citado."""
    match = _VOICE_PATTERN.match(voice.strip())
    if not match:
        raise ModelError(
            f"voz '{voice}' inválida: usa o formato <língua>-<nome>-<qualidade>, "
            "por exemplo pt_PT-tugão-medium"
        )
    family = match.group("family")
    code = f"{family}_{match.group('region')}"
    name = match.group("name")
    quality = match.group("quality")
    stem = f"{code}-{name}-{quality}"
    path = "/".join(urllib.parse.quote(part) for part in (family, code, name, quality, stem))
    base = f"{PIPER_BASE}/{path}"
    return f"{base}.onnx", f"{base}.onnx.json"


def ensure_piper_voice(
    voice: str,
    *,
    directory: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Garante que o modelo está no disco e devolve o caminho do `.onnx`."""
    target = directory or piper_dir()
    model_url, config_url = voice_urls(voice)
    remote_name = Path(urllib.parse.unquote(urllib.parse.urlparse(model_url).path)).name
    model_path = target / remote_name
    config_path = model_path.with_suffix(".onnx.json")

    if model_path.is_file() and config_path.is_file():
        return model_path

    target.mkdir(parents=True, exist_ok=True)
    for url, destination in ((model_url, model_path), (config_url, config_path)):
        if destination.is_file():
            continue
        if progress:
            progress(f"a descarregar {destination.name}")
        _download(url, destination)
    return model_path


def ensure_speaker_model(*, progress: Callable[[str], None] | None = None) -> Path:
    """Modelo de locutor (WeSpeaker, ONNX, ~25 MB). Só desce uma vez."""
    target = speaker_dir() / "model.onnx"
    if target.is_file():
        return target
    if progress:
        progress("a descarregar o modelo de voz (25 MB)")
    target.parent.mkdir(parents=True, exist_ok=True)
    _download(SPEAKER_URL, target)
    return target


def ensure_vosk_model(
    name: str = "vosk-model-small-pt-0.3",
    *,
    directory: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Garante o modelo Vosk descompactado e devolve a pasta."""
    target = (directory or vosk_dir()) / name
    if target.is_dir():
        return target

    if progress:
        progress(f"a descarregar {name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    archive = target.parent / f"{name}.zip"
    _download(f"{VOSK_BASE}/{name}.zip", archive)
    try:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(target.parent)
    except zipfile.BadZipFile as exc:
        archive.unlink(missing_ok=True)
        raise ModelError(f"o pacote {name} veio corrompido") from exc
    archive.unlink(missing_ok=True)
    return target


def _download(url: str, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=180) as response:  # noqa: S310
            partial.write_bytes(response.read())
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise ModelError(f"falha a descarregar {url}: {exc}") from exc
    partial.replace(destination)
