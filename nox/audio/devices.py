"""Escolha do microfone.

Um headset Bluetooth aparece e desaparece do sistema conforme está ligado. O
Nox prefere-o quando existe e cai para a entrada por omissão quando não existe
— sem ter de se reconfigurar a cada vez.
"""

from __future__ import annotations

from nox.optional import require

DEFAULT_NAMES = {"", "default", "omissao", "padrao"}


def input_devices() -> list[tuple[int, str]]:
    """Pares (índice, nome) das entradas disponíveis."""
    require("sounddevice")
    import sounddevice as sd

    return [
        (index, item["name"])
        for index, item in enumerate(sd.query_devices())
        if item["max_input_channels"] > 0
    ]


def match_input(preferred: str) -> int | None:
    """Índice da primeira entrada cujo nome contém `preferred`."""
    needle = preferred.strip().lower()
    if not needle or needle in DEFAULT_NAMES:
        return None
    for index, name in input_devices():
        if needle in name.lower():
            return index
    return None


def resolve_input(preferred: str, fallback: str = "default") -> tuple[int | None, str]:
    """Devolve (índice, rótulo). `None` significa a entrada por omissão."""
    index = match_input(preferred)
    if index is not None:
        return index, preferred

    fallback_index = match_input(fallback)
    if fallback_index is not None:
        return fallback_index, fallback

    return None, "default"


class DevicePicker:
    """Resolve e reescolhe o microfone, sobrevivendo a ligações Bluetooth."""

    def __init__(self, preferred: str, fallback: str = "default") -> None:
        self.preferred = preferred
        self.fallback = fallback
        self.index, self.label = resolve_input(preferred, fallback)

    def reopen(self) -> int | None:
        """Volta a procurar. Preferido primeiro, omissão depois."""
        self.index, self.label = resolve_input(self.preferred, self.fallback)
        return self.index
