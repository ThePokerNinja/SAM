"""Durable, provenance-backed session profile facts (SAM-041).

Person identity remains canonical in rm_api. This store holds only facts learned
inside a Samuel session and supports explicit owner correction.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from .episodic import memory_db_path

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_EMBED_DIMS = 96


def embed_text(text: str, *, dimensions: int = _EMBED_DIMS) -> tuple[float, ...]:
    """Create a deterministic local feature-hash vector without network I/O."""
    vector = [0.0] * dimensions
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[slot] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return tuple(vector)


@dataclass(frozen=True)
class ProfileFact:
    profile_id: str
    key: str
    value: str
    provenance: str
    confidence: float = 1.0
    corrected_by: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    id: int | None = None


class ProfileStore:
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
                CREATE TABLE IF NOT EXISTS profile_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    fact_value TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    corrected_by TEXT,
                    embedding_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(profile_id, fact_key)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_profile_facts_profile_updated "
                "ON profile_facts(profile_id, updated_at DESC)"
            )

    def upsert(self, fact: ProfileFact, *, owner_correction: bool = False) -> int:
        if owner_correction and not fact.corrected_by:
            raise ValueError("owner corrections must record corrected_by")
        embedding = json.dumps(embed_text(f"{fact.key} {fact.value}"))
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO profile_facts(
                    profile_id, fact_key, fact_value, provenance, confidence,
                    corrected_by, embedding_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id, fact_key) DO UPDATE SET
                    fact_value=excluded.fact_value,
                    provenance=excluded.provenance,
                    confidence=excluded.confidence,
                    corrected_by=excluded.corrected_by,
                    embedding_json=excluded.embedding_json,
                    updated_at=excluded.updated_at
                """,
                (
                    fact.profile_id,
                    fact.key,
                    fact.value,
                    fact.provenance,
                    max(0.0, min(1.0, fact.confidence)),
                    fact.corrected_by,
                    embedding,
                    fact.created_at,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM profile_facts WHERE profile_id=? AND fact_key=?",
                (fact.profile_id, fact.key),
            ).fetchone()
        return int(row["id"])

    async def upsert_async(self, fact: ProfileFact, *, owner_correction: bool = False) -> int:
        return await asyncio.to_thread(self.upsert, fact, owner_correction=owner_correction)

    def facts(self, profile_id: str) -> list[tuple[ProfileFact, tuple[float, ...]]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profile_facts WHERE profile_id=? ORDER BY updated_at DESC",
                (profile_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> tuple[ProfileFact, tuple[float, ...]]:
        try:
            embedding = tuple(float(value) for value in json.loads(row["embedding_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            embedding = ()
        fact = ProfileFact(
            id=int(row["id"]),
            profile_id=str(row["profile_id"]),
            key=str(row["fact_key"]),
            value=str(row["fact_value"]),
            provenance=str(row["provenance"]),
            confidence=float(row["confidence"]),
            corrected_by=row["corrected_by"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )
        return fact, embedding
