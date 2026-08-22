"""SAM-044: typed session artifacts."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass, field
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from .memory.episodic import memory_db_path

ArtifactKind = Literal[
    "notes",
    "decision",
    "action_item",
    "understanding_map",
    "next_steps",
    "summary",
    "forecast",
    "feedback",
]


@dataclass
class Artifact:
    session_id: str
    kind: ArtifactKind
    payload: dict
    credited_to: str = "samuel"
    created_at: float = field(default_factory=time.time)
    id: int | None = None


class ArtifactStore:
    def __init__(self, path=None) -> None:
        if path == ":memory:":
            self.path = None
            self._mem = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem.row_factory = sqlite3.Row
            self._init_conn(self._mem)
            return
        self.path = memory_db_path() if path is None else path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._mem = None
        self._init()

    def _connect(self) -> sqlite3.Connection:
        if self._mem is not None:
            return self._mem
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @contextmanager
    def _cx(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            if conn is not self._mem:
                conn.close()

    def _init(self) -> None:
        with self._cx() as conn:
            self._init_conn(conn)

    def _init_conn(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                credited_to TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.commit()

    def add(self, artifact: Artifact) -> int:
        with self._cx() as conn:
            cur = conn.execute(
                """
                INSERT INTO artifacts (session_id, kind, payload_json, credited_to, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    artifact.session_id,
                    artifact.kind,
                    json.dumps(artifact.payload),
                    artifact.credited_to,
                    artifact.created_at,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    async def add_async(self, artifact: Artifact) -> int:
        return await asyncio.to_thread(self.add, artifact)

    def put(self, artifact: Artifact) -> int:
        """Insert or replace the latest artifact of this kind for one session."""
        with self._cx() as conn:
            row = conn.execute(
                "SELECT id FROM artifacts WHERE session_id=? AND kind=? "
                "ORDER BY created_at DESC LIMIT 1",
                (artifact.session_id, artifact.kind),
            ).fetchone()
            if row is None:
                cur = conn.execute(
                    """
                    INSERT INTO artifacts (
                        session_id, kind, payload_json, credited_to, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.session_id,
                        artifact.kind,
                        json.dumps(artifact.payload),
                        artifact.credited_to,
                        artifact.created_at,
                    ),
                )
                artifact_id = int(cur.lastrowid)
            else:
                artifact_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE artifacts
                    SET payload_json=?, credited_to=?, created_at=?
                    WHERE id=?
                    """,
                    (
                        json.dumps(artifact.payload),
                        artifact.credited_to,
                        artifact.created_at,
                        artifact_id,
                    ),
                )
            conn.commit()
            return artifact_id

    async def put_async(self, artifact: Artifact) -> int:
        return await asyncio.to_thread(self.put, artifact)

    def list_for(self, session_id: str) -> list[Artifact]:
        with self._cx() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [
            Artifact(
                id=r["id"],
                session_id=r["session_id"],
                kind=r["kind"],
                payload=json.loads(r["payload_json"]),
                credited_to=r["credited_to"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def recent(self, *, limit: int = 20, exclude_session_id: str = "") -> list[Artifact]:
        query = "SELECT * FROM artifacts"
        params: list[object] = []
        if exclude_session_id:
            query += " WHERE session_id != ?"
            params.append(exclude_session_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))
        with self._cx() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            Artifact(
                id=row["id"],
                session_id=row["session_id"],
                kind=row["kind"],
                payload=json.loads(row["payload_json"]),
                credited_to=row["credited_to"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
