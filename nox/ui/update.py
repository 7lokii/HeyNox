"""Auto-atualização a partir do manifesto publicado nas releases.

O manifesto (`releases/latest.json`) diz qual é a versão e onde estão os
artefactos, com caminhos relativos ao próprio manifesto. Isto serve tanto o
GitHub raw como qualquer alojamento estático.

Regra que vale a pena ter escrita: **sem `sha256` no manifesto, não se aplica
nada**. Descarregar um `.exe` e correr por cima do que existe, sem conferir, é
a forma mais fácil de estragar a instalação de alguém.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from nox import __version__
from nox.paths import install_dir, user_data_dir

MANIFEST_TIMEOUT = 12.0


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "url": self.url,
            "sha256": self.sha256,
            "notes": self.notes,
        }


def _request(url: str, *, headers: dict[str, str] | None = None):
    """O único `Request` deste módulo, para o noqa ficar num sítio só."""
    return urllib.request.Request(  # noqa: S310 — ver _require_http
        url, headers=headers or {}
    )


def _open(target, timeout: float):
    """O único `urlopen` deste módulo, para o noqa ficar num sítio só."""
    return urllib.request.urlopen(target, timeout=timeout)  # noqa: S310 — ver _require_http


def platform_key() -> str:
    """A chave do manifesto que corresponde a esta máquina."""
    system = sys.platform
    machine = platform.machine().lower()
    if system.startswith("win"):
        return "windows-x64" if machine in ("amd64", "x86_64") else "windows-arm64"
    if system == "darwin":
        return "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x64"
    return "linux-x64"


def _require_http(url: str) -> None:
    """Recusa esquemas que não sejam http(s): `file:` num manifesto era um abuso."""
    if not str(url).strip().lower().startswith(("http://", "https://")):
        raise ValueError(f"endereço não permitido: {url}")


def version_tuple(text: str) -> tuple[int, ...]:
    """`0.0.2` -> (0, 0, 2). Lixo no fim não rebenta a comparação."""
    parts: list[int] = []
    for chunk in str(text).strip().split("."):
        digits = "".join(char for char in chunk if char.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def fetch_manifest(url: str, *, timeout: float = MANIFEST_TIMEOUT) -> dict[str, Any]:
    _require_http(url)
    request = _request(url, headers={"accept": "application/json"})
    with _open(request, timeout) as response:
        raw = response.read(200_000).decode("utf-8-sig", errors="replace")
    # `utf-8-sig` come o BOM que o PowerShell escreve; o json.loads não come.
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("o manifesto não é um objeto JSON")
    return data


def check(manifest_url: str, *, timeout: float = MANIFEST_TIMEOUT) -> dict[str, Any]:
    """Devolve o estado da verificação. Nunca levanta por falta de rede."""
    result: dict[str, Any] = {
        "ok": False,
        "current": __version__,
        "latest": "",
        "available": False,
        "release": None,
        "error": "",
    }
    if not manifest_url.strip():
        result["error"] = "Sem endereço de atualizações configurado."
        return result
    try:
        manifest = fetch_manifest(manifest_url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result["error"] = f"Sem ligação ao servidor de atualizações: {exc}"
        return result
    except (json.JSONDecodeError, ValueError) as exc:
        result["error"] = f"Manifesto inválido: {exc}"
        return result

    latest = str(manifest.get("version", "")).strip()
    entry = (manifest.get("platforms") or {}).get(platform_key()) or {}
    portable = entry.get("portable") if isinstance(entry, dict) else None
    checksums = manifest.get("sha256") or {}

    result["ok"] = True
    result["latest"] = latest
    if not portable:
        result["error"] = f"Não há pacote portátil para {platform_key()}."
        return result
    url = urljoin(manifest_url, str(portable))
    name = str(portable).rsplit("/", 1)[-1]
    sha = str(checksums.get(name, "")).strip().lower()
    release = Release(version=latest, url=url, sha256=sha, notes=str(manifest.get("notes", "")))
    result["release"] = release.as_dict()
    result["available"] = is_newer(latest) and bool(sha)
    if is_newer(latest) and not sha:
        result["error"] = (
            "A versão nova não tem sha256 no manifesto, por isso não é aplicada automaticamente."
        )
    return result


def writable(path: Path) -> bool:
    """Se dá para gravar nesta pasta. Os ACL do Windows enganam o `os.access`."""
    probe = path / ".nox-write-test"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def can_apply(target: Path | None = None) -> bool:
    """Só o layout portátil se atualiza sozinho."""
    target = target or install_dir()
    if not sys.platform.startswith("win"):
        return False
    return writable(target)


def download(release: Release, destination: Path) -> Path:
    """Descarrega o zip e confere o sha256 antes de devolver o caminho."""
    if not release.sha256:
        raise ValueError("o manifesto não traz sha256; recusado")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    _require_http(release.url)
    with (
        _open(release.url, 60) as response,
        partial.open("wb") as handle,
    ):
        while True:
            block = response.read(262_144)
            if not block:
                break
            digest.update(block)
            handle.write(block)
    got = digest.hexdigest()
    if got != release.sha256:
        partial.unlink(missing_ok=True)
        raise ValueError(f"sha256 não bate: esperado {release.sha256}, veio {got}")
    partial.replace(destination)
    return destination


def stage(archive: Path, workdir: Path) -> Path:
    """Descompacta num diretório de trabalho e devolve a pasta da app."""
    folder = workdir / "stage"
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as handle:
        bad = handle.testzip()
        if bad:
            raise ValueError(f"zip corrompido em {bad}")
        handle.extractall(folder)
    candidates = [item for item in folder.iterdir() if item.is_dir()]
    exe = "HeyNox.exe" if sys.platform.startswith("win") else "HeyNox"
    for candidate in candidates:
        if (candidate / exe).is_file():
            return candidate
    if (folder / exe).is_file():
        return folder
    raise ValueError("o zip não tem a pasta da aplicação")


CRLF = chr(13) + chr(10)

APPLY_SCRIPT = r"""@echo off
setlocal
set TARGET={target}
set STAGE={stage}
set LOG={log}
echo [%date% %time%] apply a espera do PID {pid} >> "%LOG%"
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
echo [%date% %time%] a copiar %STAGE% para %TARGET% >> "%LOG%"
robocopy "%STAGE%" "%TARGET%" /MIR /NFL /NDL /NJH /NJS /LOG+:"%LOG%"
if errorlevel 8 (
  echo [%date% %time%] a copia falhou. A versao antiga fica como estava. >> "%LOG%"
  exit /b 1
)
echo [%date% %time%] copia feita, a abrir a app >> "%LOG%"
start "" "%TARGET%\HeyNox.exe"
del "%~f0"
"""


def apply(release: Release, *, target: Path | None = None, workdir: Path | None = None) -> Path:
    """Descarrega, prepara e deixa um .cmd que troca a pasta quando a app sair.

    Não fecha a app: quem decide isso é a interface, depois de avisar. Devolve
    o caminho do `.cmd` para o chamador poder lançar.
    """
    target = target or install_dir()
    workdir = workdir or (user_data_dir() / "update")
    workdir.mkdir(parents=True, exist_ok=True)
    log = workdir / "apply.log"
    archive = download(release, workdir / f"HeyNox-{release.version}.zip")
    staged = stage(archive, workdir)
    script = workdir / "apply.cmd"
    filled = APPLY_SCRIPT.format(target=target, stage=staged, pid=os.getpid(), log=log)
    script.write_text(filled.replace(chr(10), CRLF), encoding="utf-8")
    return script


def launch_and_exit(script: Path) -> None:
    """Arranca o `.cmd` destacado e sai, para o script poder trocar os ficheiros."""
    # CREATE_NO_WINDOW, não DETACHED_PROCESS: sai de uma app empacotada, sem
    # consola nenhuma, e um `cmd` sem consola morre antes de correr o script.
    flags = 0
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    log = script.parent / "launch.log"
    try:
        subprocess.Popen(  # noqa: S603 — o script é escrito por nós, em dados do utilizador
            [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(script)],
            close_fds=True,
            creationflags=flags,
            cwd=str(script.parent),
        )
        log.write_text(f"lancado {script}" + chr(10), encoding="utf-8")
    except OSError as exc:
        log.write_text(f"nao consegui lancar {script}: {exc}" + chr(10), encoding="utf-8")
        return
    time.sleep(0.6)
    os._exit(0)
