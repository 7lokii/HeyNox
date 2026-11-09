"""Registo de auditoria.

Cada ação do Nox — ferramenta, argumentos, resultado, duração — fica numa linha
JSON. É o que permite responder a "o que é que ele fez?" depois do facto.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nox.paths import user_data_dir


def audit_path() -> Path:
    return user_data_dir() / "logs" / "audit.jsonl"


@dataclass
class AuditEntry:
    tool: str
    arguments: dict[str, Any]
    ok: bool
    duration_ms: int
    detail: str = ""
    at: float = field(default_factory=time.time)


class AuditLog:
    """Acrescenta entradas ao JSONL. Falhas de escrita não derrubam o Nox."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or audit_path()

    def record(self, entry: AuditEntry) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        except OSError:
            return

    def entries(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        except OSError:
            return []
        result: list[dict[str, Any]] = []
        for line in lines:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return result
