"""Gera os .spec do PyInstaller. Usado por installer/build.ps1.

Uso: python -m installer.pyinstaller

Os .spec gerados são idempotentes e chamam collect_data_files/collect_submodules
em vez de listar ficheiros à mão: assim acompanham actualizações de dependências.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = """# Gerado por installer/pyinstaller.py — não editar à mão.
# Plataforma: {platform}
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


datas = []
hiddenimports = []
binaries = []

for pkg in {voice_packages}:
    datas += collect_data_files(pkg)
    hiddenimports += collect_submodules(pkg)
{extra_hidden}{torch_block}

a = Analysis(
    ['{project_root}/scripts/{script}'],
    pathex=['{project_root}'],
    binaries=binaries,
    datas=datas + [
        ('{project_root}/config.yaml', '.'),
        ('{project_root}/nox/ui/index.html', 'nox/ui'),
    ],
    hiddenimports=hiddenimports,
    hookspath=['{project_root}/installer/hooks'],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={excludes},
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{name}',
    debug=False,
    strip=False,
    upx=False,
    console={console},
    icon='{icon}',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='{name}')
"""

VOICE_PACKAGES = """[
    'sounddevice',
    'faster_whisper',
    'ctranslate2',
    'silero_vad',
    'vosk',
    'piper',
    'edge_tts',
    'av',
    'playwright',
    'pyautogui',
    'pyperclip',
    'mss',
    'PIL',
    'winrt',
]"""

# Módulos que o collect_submodules pode não apanhar por serem namespace packages.
EXTRA_HIDDEN = """
hiddenimports += [
    'winrt.windows.media.ocr',
    'winrt.windows.graphics.imaging',
    'winrt.windows.storage.streams',
    'winrt.windows.foundation',
]
"""

NO_PACKAGES = "[]"

TORCH_BLOCK = """
import torch  # hooks do PyInstaller recolhem as DLLs

hiddenimports += ['torch']
try:
    import torchaudio  # noqa: F401

    hiddenimports += ['torchaudio']
except ImportError:
    pass
if sys.platform == 'win32':
    # O fork CPU do torch carrega torch_cpu.dll de forma dinâmica à procura de
    # diretórios adicionais em TORCH_LIB.
    os.environ['TORCH_LIB'] = os.path.dirname(torch.__file__)
"""

TORCH_EXCLUDES = "['torch', 'torchaudio']"


def build_spec(name: str, script: str, console: bool, with_voice: bool) -> Path:
    icon = PROJECT_ROOT / "installer" / "icon.ico"
    spec = TEMPLATE.format(
        platform=sys.platform,
        script=script,
        project_root=PROJECT_ROOT.as_posix(),
        name=name,
        console=console,
        icon=icon.as_posix() if icon.is_file() else "",
        excludes="[]" if with_voice else TORCH_EXCLUDES,
        voice_packages=VOICE_PACKAGES if with_voice else NO_PACKAGES,
        extra_hidden=EXTRA_HIDDEN if with_voice else "",
        torch_block=TORCH_BLOCK if with_voice else "",
    )
    out = PROJECT_ROOT / "installer" / f"{name}.spec"
    out.write_text(spec, encoding="utf-8")
    return out


def main() -> int:
    for path in (
        build_spec("nox", "nox_cli.py", console=True, with_voice=False),
        build_spec("HeyNox", "heynox_app.py", console=False, with_voice=True),
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
