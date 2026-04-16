"""Database — SQLite CRUD"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .models import (
    FileRecord,
    MemoryEntry,
    MessageRecord,
    Session,
    SnapshotRecord,
    new_id,
    now_iso,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT 'New Session',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    agent_type TEXT DEFAULT 'main',
    settings TEXT DEFAULT '{}',
    total_tokens INTEGER DEFAULT 0,
    total_cost REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,
    tool_results TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    parent_id TEXT,
    description TEXT NOT NULL,
    tool_calls TEXT,
    diff TEXT,
    file_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES snapshots(id)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots(session_id, created_at);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    UNIQUE(session_id, category, key)
);

CREATE TABLE IF NOT EXISTS file_records (
    file_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_hash TEXT NOT NULL,
    file_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    working_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    preload_status TEXT DEFAULT 'pending',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_file_records_session ON file_records(session_id);
"""


def _json_dumps(obj: Any) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s: str | None) -> Any:
    if s is None:
        return None
    return json.loads(s)


class Database:
    """SQLite 数据库操作"""

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        # executescript 可能重置 PRAGMA，在之后设置
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------ #
    #  Session
    # ------------------------------------------------------------------ #

    def create_session(self, name: str = "New Session") -> Session:
        sid = new_id()
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO sessions (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (sid, name, ts, ts),
        )
        self.conn.commit()
        return Session(id=sid, name=name, created_at=ts, updated_at=ts)

    def get_session(self, session_id: str) -> Session | None:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        return Session(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            agent_type=row["agent_type"] or "main",
            settings=_json_loads(row["settings"]) or {},
            total_tokens=row["total_tokens"] or 0,
            total_cost=row["total_cost"] or 0.0,
        )

    def list_sessions(self, limit: int = 50) -> list[Session]:
        rows = self.conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def update_session(self, session_id: str, **kwargs) -> None:
        allowed = {"name", "agent_type", "settings", "total_tokens", "total_cost"}
        parts: list[str] = []
        values: list[Any] = []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            if k == "settings":
                v = _json_dumps(v)
            parts.append(f"{k} = ?")
            values.append(v)
        if not parts:
            return
        parts.append("updated_at = ?")
        values.append(now_iso())
        values.append(session_id)
        self.conn.execute(
            f"UPDATE sessions SET {', '.join(parts)} WHERE id = ?", values
        )
        self.conn.commit()

    def delete_session(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.commit()

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            agent_type=row["agent_type"] or "main",
            settings=_json_loads(row["settings"]) or {},
            total_tokens=row["total_tokens"] or 0,
            total_cost=row["total_cost"] or 0.0,
        )

    # ------------------------------------------------------------------ #
    #  Messages
    # ------------------------------------------------------------------ #

    def save_message(self, msg: MessageRecord) -> None:
        self.conn.execute(
            """INSERT INTO messages
               (id, session_id, role, content, tool_calls, tool_results,
                tokens_in, tokens_out, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.id, msg.session_id, msg.role, msg.content,
                _json_dumps(msg.tool_calls), _json_dumps(msg.tool_results),
                msg.tokens_in, msg.tokens_out,
                msg.created_at or now_iso(),
            ),
        )
        self.conn.commit()

    def get_messages(
        self,
        session_id: str,
        limit: int = 50,
        before: str | None = None,
    ) -> list[MessageRecord]:
        if before:
            rows = self.conn.execute(
                """SELECT * FROM messages
                   WHERE session_id = ? AND created_at < ?
                   ORDER BY created_at DESC LIMIT ?""",
                (session_id, before, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM messages
                   WHERE session_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        # 按时间正序返回
        return [self._row_to_message(r) for r in reversed(rows)]

    def get_recent_messages(
        self, session_id: str, count: int = 10
    ) -> list[MessageRecord]:
        rows = self.conn.execute(
            """SELECT * FROM messages
               WHERE session_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (session_id, count),
        ).fetchall()
        return [self._row_to_message(r) for r in reversed(rows)]

    def delete_old_messages(self, session_id: str, keep_recent: int = 100) -> int:
        # 找到需要保留的最新 N 条消息的最早 created_at
        row = self.conn.execute(
            """SELECT created_at FROM messages
               WHERE session_id = ?
               ORDER BY created_at DESC
               LIMIT 1 OFFSET ?""",
            (session_id, keep_recent - 1),
        ).fetchone()
        if not row:
            return 0
        cutoff = row["created_at"]
        cur = self.conn.execute(
            "DELETE FROM messages WHERE session_id = ? AND created_at < ?",
            (session_id, cutoff),
        )
        self.conn.commit()
        return cur.rowcount

    def _row_to_message(self, row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            tool_calls=_json_loads(row["tool_calls"]),
            tool_results=_json_loads(row["tool_results"]),
            tokens_in=row["tokens_in"] or 0,
            tokens_out=row["tokens_out"] or 0,
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------ #
    #  Snapshots
    # ------------------------------------------------------------------ #

    def create_snapshot(self, snap: SnapshotRecord) -> None:
        self.conn.execute(
            """INSERT INTO snapshots
               (id, session_id, file_id, parent_id, description,
                tool_calls, diff, file_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snap.id, snap.session_id, snap.file_id, snap.parent_id,
                snap.description, _json_dumps(snap.tool_calls),
                _json_dumps(snap.diff), snap.file_hash,
                snap.created_at or now_iso(),
            ),
        )
        self.conn.commit()

    def get_snapshot(self, snapshot_id: str) -> SnapshotRecord | None:
        row = self.conn.execute(
            "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_snapshot(row)

    def get_snapshot_chain(
        self, session_id: str, file_id: str
    ) -> list[SnapshotRecord]:
        rows = self.conn.execute(
            """SELECT * FROM snapshots
               WHERE session_id = ? AND file_id = ?
               ORDER BY created_at ASC""",
            (session_id, file_id),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def get_latest_snapshot(
        self, session_id: str, file_id: str
    ) -> SnapshotRecord | None:
        row = self.conn.execute(
            """SELECT * FROM snapshots
               WHERE session_id = ? AND file_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (session_id, file_id),
        ).fetchone()
        if not row:
            return None
        return self._row_to_snapshot(row)

    def get_children(self, snapshot_id: str) -> list[SnapshotRecord]:
        rows = self.conn.execute(
            "SELECT * FROM snapshots WHERE parent_id = ? ORDER BY created_at ASC",
            (snapshot_id,),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def _row_to_snapshot(self, row: sqlite3.Row) -> SnapshotRecord:
        return SnapshotRecord(
            id=row["id"],
            session_id=row["session_id"],
            file_id=row["file_id"],
            parent_id=row["parent_id"],
            description=row["description"],
            tool_calls=_json_loads(row["tool_calls"]),
            diff=_json_loads(row["diff"]) or {},
            file_hash=row["file_hash"] or "",
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------ #
    #  Memories
    # ------------------------------------------------------------------ #

    def save_memory(
        self, session_id: str, category: str, key: str, value: Any
    ) -> None:
        value_json = _json_dumps(value)
        ts = now_iso()
        # Upsert: INSERT OR REPLACE
        existing = self.conn.execute(
            "SELECT id FROM memories WHERE session_id = ? AND category = ? AND key = ?",
            (session_id, category, key),
        ).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE memories SET value = ?, updated_at = ? WHERE id = ?",
                (value_json, ts, existing["id"]),
            )
        else:
            self.conn.execute(
                """INSERT INTO memories (id, session_id, category, key, value, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (new_id(), session_id, category, key, value_json, ts, ts),
            )
        self.conn.commit()

    def get_memory(
        self, session_id: str, category: str, key: str
    ) -> Any | None:
        row = self.conn.execute(
            "SELECT value FROM memories WHERE session_id = ? AND category = ? AND key = ?",
            (session_id, category, key),
        ).fetchone()
        if not row:
            return None
        return _json_loads(row["value"])

    def list_memories(
        self, session_id: str, category: str | None = None
    ) -> list[MemoryEntry]:
        if category:
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE session_id = ? AND category = ?",
                (session_id, category),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            session_id=row["session_id"],
            category=row["category"],
            key=row["key"],
            value=_json_loads(row["value"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ------------------------------------------------------------------ #
    #  File Records
    # ------------------------------------------------------------------ #

    def save_file_record(self, record: FileRecord) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO file_records
               (file_id, session_id, file_name, file_size, file_hash,
                file_type, source_path, working_path, created_at, preload_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.file_id, record.session_id, record.file_name,
                record.file_size, record.file_hash, record.file_type,
                record.source_path, record.working_path,
                record.created_at or now_iso(), record.preload_status,
            ),
        )
        self.conn.commit()

    def get_file_record(self, file_id: str) -> FileRecord | None:
        row = self.conn.execute(
            "SELECT * FROM file_records WHERE file_id = ?", (file_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_file_record(row)

    def list_file_records(self, session_id: str) -> list[FileRecord]:
        rows = self.conn.execute(
            "SELECT * FROM file_records WHERE session_id = ?", (session_id,)
        ).fetchall()
        return [self._row_to_file_record(r) for r in rows]

    def update_preload_status(self, file_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE file_records SET preload_status = ? WHERE file_id = ?",
            (status, file_id),
        )
        self.conn.commit()

    def _row_to_file_record(self, row: sqlite3.Row) -> FileRecord:
        return FileRecord(
            file_id=row["file_id"],
            session_id=row["session_id"],
            file_name=row["file_name"],
            file_size=row["file_size"],
            file_hash=row["file_hash"],
            file_type=row["file_type"],
            source_path=row["source_path"],
            working_path=row["working_path"],
            created_at=row["created_at"],
            preload_status=row["preload_status"],
        )
