"""Confina o Nox ao que lhe é permitido tocar.

Duas regras, ambas do lado do servidor — nunca a pedido do modelo:

- **Caminhos**: só dentro de `security.allowed_paths`, e nunca em
  `security.blocked_paths` (`.env`, `.git`, credenciais).
- **Comandos**: só os que começam por um prefixo de `security.allowed_commands`,
  sem metacaracteres de shell que permitam encadear outro comando.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from nox.config import Config, NoxError

# Tudo o que permite juntar um segundo comando ao primeiro.
_SHELL_META = set(";&|`$><\n")


class SandboxError(NoxError):
    """A operação pedida está fora do que o Nox pode fazer."""


class Sandbox:
    def __init__(self, config: Config, root: Path | None = None) -> None:
        self.root = (root or Path.cwd()).resolve()
        self.allowed_paths = [self._resolve(path) for path in config.security.allowed_paths]
        self.blocked = [name.lower() for name in config.security.blocked_paths]
        self.allowed_commands = [command.strip() for command in config.security.allowed_commands]
        self.blocked_commands = [
            command.strip().lower() for command in config.security.blocked_commands
        ]

    # --- caminhos -------------------------------------------------------

    def resolve(self, path: str) -> Path:
        """Resolve e valida um caminho para leitura/escrita."""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise SandboxError(f"caminho inválido: {path}") from exc

        if any(part.lower() in self.blocked for part in resolved.parts):
            raise SandboxError(f"{path} está numa pasta bloqueada")

        if not any(_is_within(resolved, allowed) for allowed in self.allowed_paths):
            raise SandboxError(f"{path} está fora das pastas autorizadas")

        return resolved

    def _resolve(self, path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (self.root / path).resolve()

    # --- comandos -------------------------------------------------------

    def parse_command(self, command: str) -> list[str]:
        """Valida a forma do comando, sem olhar à lista de permitidos.

        É o que uma aprovação **não** pode contornar: metacaracteres de shell e
        comandos destrutivos ficam de fora mesmo que o utilizador aprove.
        """
        command = " ".join(command.split())
        if not command:
            raise SandboxError("comando vazio")

        if any(char in _SHELL_META for char in command):
            raise SandboxError(
                "o comando tem caracteres de shell (; | & > $ `) — só um comando de cada vez"
            )

        lowered = command.lower()
        for blocked in self.blocked_commands:
            if blocked and (lowered == blocked or lowered.startswith(blocked + " ")):
                raise SandboxError(f"'{command}' é destrutivo e está bloqueado")

        try:
            return shlex.split(command)
        except ValueError as exc:
            raise SandboxError(f"comando inválido: {exc}") from exc

    def is_allowed_command(self, command: str) -> bool:
        normalized = " ".join(command.split())
        return any(normalized.startswith(prefix) for prefix in self.allowed_commands)

    def check_command(self, command: str) -> list[str]:
        """Devolve o comando já dividido em argumentos, ou levanta erro."""
        normalized = " ".join(command.split())
        if not self.is_allowed_command(normalized):
            permitidos = ", ".join(self.allowed_commands) or "(nenhum)"
            raise SandboxError(
                f"'{normalized}' não está na lista de comandos permitidos. Permitidos: {permitidos}"
            )
        return self.parse_command(normalized)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
