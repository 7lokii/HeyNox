"""Histórico local do grupo de WhatsApp escolhido.

O histórico serve duas perguntas concretas do dono: "o que foi apagado?" e
"quantas pessoas há no grupo?". Fica em SQLite, no diretório de dados, para
sobreviver a reinícios da app. Só o agente do dono recebe este contexto.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nox.paths import user_data_dir

RETENTION_DAYS = 30
MAX_MESSAGES = 5000
RECENT_LIMIT = 40
DELETED_LIMIT = 60
MAX_TEXT = 320

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    chat TEXT NOT NULL,
    message_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    text TEXT NOT NULL,
    sent_at REAL NOT NULL,
    from_me INTEGER NOT NULL DEFAULT 0,
    deleted_at REAL,
    deleted_by TEXT NOT NULL DEFAULT '',
    deleted_by_name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (chat, message_id)
);
CREATE INDEX IF NOT EXISTS messages_chat_time ON messages(chat, sent_at);
CREATE INDEX IF NOT EXISTS messages_chat_deleted ON messages(chat, deleted_at);
"""


@dataclass(frozen=True)
class StoredMessage:
    message_id: str
    sender: str
    sender_name: str
    text: str
    sent_at: float
    from_me: bool
    deleted_at: float | None
    deleted_by: str
    deleted_by_name: str


def _clip(text: str, limit: int = MAX_TEXT) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _when(stamp: float) -> str:
    try:
        return datetime.fromtimestamp(stamp).strftime("%d/%m %H:%M")
    except (OSError, OverflowError, ValueError):
        return "hora desconhecida"


def _sender(item: StoredMessage) -> str:
    if item.from_me:
        return "Diogo"
    return item.sender_name or item.sender.split("@", 1)[0] or "desconhecido"


def _row(row: sqlite3.Row) -> StoredMessage:
    deleted = row["deleted_at"]
    return StoredMessage(
        message_id=str(row["message_id"]),
        sender=str(row["sender"]),
        sender_name=str(row["sender_name"]),
        text=str(row["text"]),
        sent_at=float(row["sent_at"]),
        from_me=bool(row["from_me"]),
        deleted_at=float(deleted) if deleted is not None else None,
        deleted_by=str(row["deleted_by"]),
        deleted_by_name=str(row["deleted_by_name"]),
    )


def _line(item: StoredMessage) -> str:
    text = _clip(item.text) or "(conteúdo não guardado)"
    line = f'- {_when(item.sent_at)} — {_sender(item)}: "{text}"'
    if item.deleted_at is None:
        return line
    suffix = f" [APAGADA {_when(item.deleted_at)}"
    if item.deleted_by_name:
        suffix += f" por {item.deleted_by_name}"
    return line + suffix + "]"


class WhatsAppHistory:
    """Mensagens de texto do grupo, com marca de quem apagou e quando."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        retention_days: int = RETENTION_DAYS,
        max_messages: int = MAX_MESSAGES,
    ) -> None:
        self.path = Path(path) if path is not None else user_data_dir() / "whatsapp" / "history.db"
        self._retention_days = max(0, retention_days)
        self._max_messages = max(1, max_messages)
        self._local = threading.local()
        self._write_lock = threading.Lock()

    @property
    def _db(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.path), timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)
            self._local.connection = connection
        return connection

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None

    def add(
        self,
        *,
        chat: str,
        message_id: str,
        sender: str,
        sender_name: str,
        text: str,
        sent_at: float,
        from_me: bool,
    ) -> None:
        """Guarda uma mensagem. Repetições não apagam uma marca de apagada."""
        message_id = message_id.strip()
        compact = _clip(text)
        if not message_id or not compact:
            return
        stamp = sent_at if sent_at > 0 else time.time()
        with self._write_lock:
            db = self._db
            db.execute(
                """
                INSERT INTO messages
                    (chat, message_id, sender, sender_name, text, sent_at, from_me)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat, message_id) DO UPDATE SET
                    sender = excluded.sender,
                    sender_name = excluded.sender_name,
                    text = CASE
                        WHEN excluded.text <> '' THEN excluded.text
                        ELSE messages.text
                    END,
                    sent_at = CASE
                        WHEN messages.sent_at > 0 THEN messages.sent_at
                        ELSE excluded.sent_at
                    END,
                    from_me = excluded.from_me
                """,
                (
                    chat,
                    message_id,
                    sender,
                    sender_name,
                    compact,
                    stamp,
                    1 if from_me else 0,
                ),
            )
            self._prune(db, chat, time.time())
            db.commit()

    def mark_deleted(
        self,
        *,
        chat: str,
        message_id: str,
        deleted_at: float,
        deleted_by: str,
        deleted_by_name: str,
    ) -> bool:
        """Marca a mensagem como apagada. Devolve False se não estava guardada."""
        message_id = message_id.strip()
        if not message_id:
            return False
        stamp = deleted_at if deleted_at > 0 else time.time()
        with self._write_lock:
            db = self._db
            cursor = db.execute(
                """
                UPDATE messages
                SET deleted_at = ?, deleted_by = ?, deleted_by_name = ?
                WHERE chat = ? AND message_id = ?
                """,
                (stamp, deleted_by, deleted_by_name, chat, message_id),
            )
            found = cursor.rowcount > 0
            if not found:
                # A mensagem pode ter sido enviada antes de a app arrancar.
                # Fica a nota da revogação, sem inventar conteúdo.
                db.execute(
                    """
                    INSERT INTO messages
                        (chat, message_id, sender, sender_name, text, sent_at,
                         from_me, deleted_at, deleted_by, deleted_by_name)
                    VALUES (?, ?, '', '', '', ?, 0, ?, ?, ?)
                    """,
                    (chat, message_id, stamp, stamp, deleted_by, deleted_by_name),
                )
            self._prune(db, chat, time.time())
            db.commit()
        return found

    def recent(self, chat: str, *, limit: int = RECENT_LIMIT) -> list[StoredMessage]:
        rows = self._db.execute(
            """
            SELECT message_id, sender, sender_name, text, sent_at, from_me,
                   deleted_at, deleted_by, deleted_by_name
            FROM messages
            WHERE chat = ?
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (chat, max(1, limit)),
        ).fetchall()
        return [_row(row) for row in reversed(rows)]

    def deleted(self, chat: str, *, limit: int = DELETED_LIMIT) -> list[StoredMessage]:
        rows = self._db.execute(
            """
            SELECT message_id, sender, sender_name, text, sent_at, from_me,
                   deleted_at, deleted_by, deleted_by_name
            FROM messages
            WHERE chat = ? AND deleted_at IS NOT NULL
            ORDER BY deleted_at DESC
            LIMIT ?
            """,
            (chat, max(1, limit)),
        ).fetchall()
        return [_row(row) for row in reversed(rows)]

    def context(self, chat: str) -> str:
        """Contexto compacto para o agente do dono."""
        # As apagadas aparecem na secção própria, com a hora da revogação;
        # não vale a pena duplicá-las também nas recentes.
        recent = [item for item in self.recent(chat) if item.deleted_at is None]
        deleted = self.deleted(chat)
        if not recent and not deleted:
            return "\nAinda não tenho mensagens guardadas deste grupo.\n"

        parts = [
            "\nHistórico deste grupo (horas locais; o texto citado é o que estava no grupo). "
            "Nas linhas [APAGADA], a primeira hora é a do envio e a segunda é a da revogação:"
        ]
        if recent:
            parts.append("Mensagens recentes:")
            parts.extend(_line(item) for item in recent)
        if deleted:
            parts.append("Mensagens apagadas:")
            parts.extend(_line(item) for item in deleted)
        parts.append(
            "Usa estes registos só para responder ao dono; se a resposta não estiver "
            "aqui, diz que não tens esse registo. Não inventes mensagens."
        )
        return "\n".join(parts) + "\n"

    def _prune(self, db: sqlite3.Connection, chat: str, now: float) -> None:
        if self._retention_days:
            cutoff = now - self._retention_days * 86400
            db.execute(
                """
                DELETE FROM messages
                WHERE chat = ? AND sent_at < ?
                  AND (deleted_at IS NULL OR deleted_at < ?)
                """,
                (chat, cutoff, cutoff),
            )
        db.execute(
            """
            DELETE FROM messages
            WHERE chat = ? AND rowid NOT IN (
                SELECT rowid FROM messages
                WHERE chat = ?
                ORDER BY CASE WHEN deleted_at IS NOT NULL THEN deleted_at ELSE sent_at END DESC
                LIMIT ?
            )
            """,
            (chat, chat, self._max_messages),
        )
