"""Durable KPI and explicit owner-consent seam for SkillBuilder (SAM-053)."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from ..memory.episodic import memory_db_path
from .models import KPISnapshot, SkillCandidate
from .scoring import evaluate_candidate
from .states import CandidateStatus


class SkillBuilderRuntime:
    """Persist evidence and default-deny adoption until owner consent is recorded."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else memory_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS skill_kpis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    observed_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_skill_kpis_latest
                    ON skill_kpis(skill_id, metric_name, observed_at DESC);
                CREATE TABLE IF NOT EXISTS skill_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_consent (
                    candidate_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    decided_by TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    decided_at REAL NOT NULL
                );
                """
            )

    def record_kpi(self, skill_id: str, snapshot: KPISnapshot) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO skill_kpis(skill_id, metric_name, snapshot_json, observed_at) "
                "VALUES (?, ?, ?, ?)",
                (skill_id, snapshot.metric_name, json.dumps(asdict(snapshot)), time.time()),
            )
            return int(cur.lastrowid)

    def latest_kpis(self, skill_id: str) -> dict[str, KPISnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT metric_name, snapshot_json FROM skill_kpis k
                WHERE skill_id=? AND observed_at=(
                    SELECT MAX(observed_at) FROM skill_kpis
                    WHERE skill_id=k.skill_id AND metric_name=k.metric_name
                )
                """,
                (skill_id,),
            ).fetchall()
        return {
            str(row["metric_name"]): KPISnapshot(**json.loads(row["snapshot_json"]))
            for row in rows
        }

    def record_consent(
        self,
        candidate_id: str,
        *,
        approved: bool,
        decided_by: str,
        evidence_ref: str,
    ) -> None:
        if not decided_by.strip() or not evidence_ref.strip():
            raise ValueError("consent requires actor and evidence reference")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO skill_consent(candidate_id, status, decided_by, evidence_ref, decided_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    status=excluded.status,
                    decided_by=excluded.decided_by,
                    evidence_ref=excluded.evidence_ref,
                    decided_at=excluded.decided_at
                """,
                (
                    candidate_id,
                    "approved" if approved else "denied",
                    decided_by,
                    evidence_ref,
                    time.time(),
                ),
            )

    def consent_status(self, candidate_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM skill_consent WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        return str(row["status"]) if row else "missing"

    def request_approval(self, candidate_id: str, *, reason: str, trust_tier: str = "T1") -> dict:
        """Emit APPROVAL_NEEDED for Hermes/studios consent (SAM-053 remaining loop)."""
        payload = {
            "event": "APPROVAL_NEEDED",
            "candidate_id": candidate_id,
            "reason": reason,
            "trust_tier": trust_tier,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO skill_events(candidate_id, event, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (candidate_id, "APPROVAL_NEEDED", json.dumps(payload), time.time()),
            )
        return payload

    def approve_for_implementation(self, candidate: SkillCandidate) -> SkillCandidate:
        """Advance only when both deterministic gates and explicit consent pass."""
        evaluate_candidate(candidate)
        if not candidate.gates.approved_for_adoption:
            candidate.status = CandidateStatus.NEEDS_MORE_DATA
            return candidate
        if self.consent_status(candidate.candidate_id) != "approved":
            candidate.status = CandidateStatus.UNDER_REVIEW
            return candidate
        candidate.status = CandidateStatus.APPROVED
        candidate.updated_at = time.time()
        return candidate
