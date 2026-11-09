"""Memória do Nox em SQLite.

Duas tabelas e um índice FTS5: os turnos da conversa e os factos que o Nox
decide guardar. Sem Chroma nem embeddings — a pesquisa por palavra resolve o
caso real ("lembra-te do projeto X") e não acrescenta dependências.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nox.config import Config, NoxError
from nox.paths import user_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session, id);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    text, content='facts', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


class MemoryError(NoxError):
    """A base de memória não abriu ou está corrompida."""


def resolve_memory_path(config: Config) -> Path:
    r"""Caminho absoluto do ficheiro de memória.

    Relativo resolve em `%LOCALAPPDATA%\HeyNox`: a pasta de instalação não é
    escrita e o utilizador não deve perder a memória ao atualizar.
    """
    path = config.memory.sqlite_path
    return path if path.is_absolute() else user_data_dir() / path


@dataclass(frozen=True)
class Fact:
    id: int
    kind: str
    text: str


class MemoryStore:
    """Histórico de conversa e factos duráveis."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._local = threading.local()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MemoryError(f"não consegui criar {self.path.parent}: {exc}") from exc
        # Abre já, para falhar no arranque e não no primeiro turno.
        _ = self._db

    @property
    def _db(self) -> sqlite3.Connection:
        """Uma ligação por thread.

        O SQLite recusa ligações partilhadas entre threads, e a interface serve
        pedidos em várias. `check_same_thread=False` sozinho não chegava: cada
        thread precisa da sua.
        """
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._open()
            self._local.connection = connection
        return connection

    def _open(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(str(self.path), timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)
        except sqlite3.Error as exc:
            raise MemoryError(f"não consegui abrir a memória em {self.path}: {exc}") from exc
        return connection

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None

    # --- conversa -------------------------------------------------------

    def add_turn(self, session: str, role: str, text: str) -> None:
        if not text.strip():
            return
        self._db.execute(
            "INSERT INTO turns (session, role, text, created_at) VALUES (?, ?, ?, ?)",
            (session, role, text, time.time()),
        )
        self._db.commit()

    def recent_turns(self, session: str, limit: int = 12) -> list[tuple[str, str]]:
        rows = self._db.execute(
            "SELECT role, text FROM turns WHERE session = ? ORDER BY id DESC LIMIT ?",
            (session, limit),
        ).fetchall()
        return [(row["role"], row["text"]) for row in reversed(rows)]

    def count_turns(self) -> int:
        return int(self._db.execute("SELECT count(*) FROM turns").fetchone()[0])

    def clear_turns(self, session: str | None = None) -> int:
        if session is None:
            cursor = self._db.execute("DELETE FROM turns")
        else:
            cursor = self._db.execute("DELETE FROM turns WHERE session = ?", (session,))
        self._db.commit()
        return cursor.rowcount

    # --- factos ---------------------------------------------------------

    def add_fact(self, kind: str, text: str) -> bool:
        """Guarda um facto. Devolve False se já existia igual."""
        text = " ".join(text.split())
        if not text:
            return False
        exists = self._db.execute(
            "SELECT 1 FROM facts WHERE lower(text) = lower(?)", (text,)
        ).fetchone()
        if exists:
            return False
        self._db.execute(
            "INSERT INTO facts (kind, text, created_at) VALUES (?, ?, ?)",
            (kind, text, time.time()),
        )
        self._db.commit()
        return True

    def facts(self, *, limit: int = 100) -> list[Fact]:
        rows = self._db.execute(
            "SELECT id, kind, text FROM facts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Fact(row["id"], row["kind"], row["text"]) for row in rows]

    def search(self, query: str, *, limit: int = 5) -> list[Fact]:
        """Pesquisa por palavra. Devolve vazio se a query não tiver termos."""
        match = _match_expression(query)
        if not match:
            return []
        try:
            rows = self._db.execute(
                """
                SELECT f.id, f.kind, f.text
                FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid
                WHERE facts_fts MATCH ?
                ORDER BY rank LIMIT ?
                """,
                (match, limit),
            ).fetchall()
        except sqlite3.Error:
            return []
        return [Fact(row["id"], row["kind"], row["text"]) for row in rows]

    def forget(self, pattern: str) -> int:
        cursor = self._db.execute("DELETE FROM facts WHERE text LIKE ?", (f"%{pattern.strip()}%",))
        self._db.commit()
        return cursor.rowcount

    def clear_facts(self) -> int:
        cursor = self._db.execute("DELETE FROM facts")
        self._db.commit()
        return cursor.rowcount

    # --- exportar / importar --------------------------------------------

    def export(self) -> dict[str, Any]:
        turns = [
            dict(row)
            for row in self._db.execute(
                "SELECT session, role, text, created_at FROM turns ORDER BY id"
            )
        ]
        facts = [
            dict(row)
            for row in self._db.execute("SELECT kind, text, created_at FROM facts ORDER BY id")
        ]
        return {"version": 1, "turns": turns, "facts": facts}

    def import_data(self, payload: dict[str, Any]) -> tuple[int, int]:
        """Importa sem duplicar. Devolve (turnos novos, factos novos)."""
        turns = 0
        for item in payload.get("turns") or []:
            self._db.execute(
                "INSERT INTO turns (session, role, text, created_at) VALUES (?, ?, ?, ?)",
                (
                    str(item.get("session", "local")),
                    str(item.get("role", "user")),
                    str(item.get("text", "")),
                    float(item.get("created_at") or time.time()),
                ),
            )
            turns += 1
        facts = sum(
            1
            for item in payload.get("facts") or []
            if self.add_fact(str(item.get("kind", "nota")), str(item.get("text", "")))
        )
        self._db.commit()
        return turns, facts

    def save_to(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.export(), ensure_ascii=False, indent=2), "utf-8")
        return target

    def load_from(self, path: Path | str) -> tuple[int, int]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MemoryError(f"não consegui ler {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise MemoryError(f"{path} não tem o formato esperado")
        return self.import_data(payload)


def _match_expression(query: str) -> str:
    """Constrói uma expressão FTS5 segura a partir de texto livre."""
    tokens = ["".join(ch for ch in word if ch.isalnum()) for word in query.lower().split()]
    tokens = [token for token in tokens if len(token) > 2][:8]
    return " OR ".join(f'"{token}"' for token in tokens)
