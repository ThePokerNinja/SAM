"""SQLite-backed, session-scoped episodic memory (SAM-040).

Writes are designed to run through ``asyncio.to_thread`` after a turn so SQLite
never sits on the realtime reply path.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def memory_db_path() -> Path:
    explicit = os.getenv("SAM_MEMORY_DB", "").strip()
    if explicit:
        path = Path(explicit)
    else:
        root = Path(os.getenv("SAM_CACHE_DIR") or os.getenv("RM_CACHE_DIR") or Path.cwd())
        path = root / "sam_memory.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class Episode:
    session_id: str
    kind: str
    content: str
    speaker_id: str | None = None
    summary: str | None = None
    decisions: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    provenance: str = "live_session"
    created_at: float = field(default_factory=time.time)
    id: int | None = None


class EpisodicMemoryStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else memory_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    speaker_id TEXT,
                    summary TEXT,
                    decisions_json TEXT NOT NULL DEFAULT '[]',
                    artifact_refs_json TEXT NOT NULL DEFAULT '[]',
                    provenance TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodes_session_created "
                "ON episodes(session_id, created_at DESC)"
            )

    def append(self, episode: Episode) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO episodes(
                    session_id, kind, content, speaker_id, summary,
                    decisions_json, artifact_refs_json, provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.session_id,
                    episode.kind,
                    episode.content,
                    episode.speaker_id,
                    episode.summary,
                    json.dumps(list(episode.decisions)),
                    json.dumps(list(episode.artifact_refs)),
                    episode.provenance,
                    episode.created_at,
                ),
            )
            return int(cur.lastrowid)

    async def append_async(self, episode: Episode) -> int:
        return await asyncio.to_thread(self.append, episode)

    def recent(self, session_id: str, *, limit: int = 20) -> list[Episode]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM episodes WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, max(1, limit)),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def all_recent(self, *, limit: int = 100) -> list[Episode]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Episode:
        def _tuple(raw: str) -> tuple[str, ...]:
            try:
                value: Any = json.loads(raw)
                return tuple(str(item) for item in value) if isinstance(value, list) else ()
            except (TypeError, json.JSONDecodeError):
                return ()

        return Episode(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            kind=str(row["kind"]),
            content=str(row["content"]),
            speaker_id=row["speaker_id"],
            summary=row["summary"],
            decisions=_tuple(row["decisions_json"]),
            artifact_refs=_tuple(row["artifact_refs_json"]),
            provenance=str(row["provenance"]),
            created_at=float(row["created_at"]),
        )
