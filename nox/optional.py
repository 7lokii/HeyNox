"""Acesso a dependências opcionais.

As dependências pesadas (áudio, modelos) vivem em extras do pyproject e só são
importadas quando a funcionalidade que as usa é chamada. Assim o núcleo e os
testes correm sem modelos, GPU ou microfone.
"""

from __future__ import annotations

import importlib
from types import ModuleType

_EXTRAS = {
    "faster_whisper": "stt",
    "openwakeword": "wake",
    "silero_vad": "vad",
    "torch": "vad",
    "kokoro": "tts",
    "sounddevice": "audio",
    "numpy": "audio",
}


class OptionalDependencyError(ImportError):
    """Dependência opcional não instalada."""


def require(module_name: str) -> ModuleType:
    """Importa um módulo ou levanta OptionalDependencyError com a instrução de instalação."""
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        extra = _EXTRAS.get(module_name)
        hint = f" (pip install -e .[{extra}])" if extra else ""
        raise OptionalDependencyError(
            f"A dependência opcional '{module_name}' não está instalada{hint}"
        ) from exc


def available(module_name: str) -> bool:
    """Diz se um módulo opcional pode ser importado, sem o manter em cache de erro."""
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True
