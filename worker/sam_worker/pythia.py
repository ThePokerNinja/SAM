"""Pythia prediction seam (SAM-073..076). Never inline on the voice turn."""

from __future__ import annotations

import asyncio
import json
import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Forecast:
    subject: str
    horizon: str
    value: float
    confidence: float
    drivers: tuple[str, ...]
    provenance: str
    created_at: float = field(default_factory=time.time)

    def as_artifact(self) -> dict[str, Any]:
        return {
            "kind": "forecast",
            "subject": self.subject,
            "horizon": self.horizon,
            "value": self.value,
            "confidence": self.confidence,
            "drivers": list(self.drivers),
            "provenance": self.provenance,
        }


class BaselineStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self._values: dict[str, list[float]] = {}
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pythia_baselines (
                        subject TEXT NOT NULL,
                        value REAL NOT NULL,
                        observed_at REAL NOT NULL
                    )
                    """
                )

    def observe(self, subject: str, value: float) -> None:
        numeric = float(value)
        if self.path is None:
            self._values.setdefault(subject, []).append(numeric)
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO pythia_baselines(subject, value, observed_at) VALUES (?, ?, ?)",
                (subject, numeric, time.time()),
            )

    async def observe_async(self, subject: str, value: float) -> None:
        await asyncio.to_thread(self.observe, subject, value)

    def zscore(self, subject: str, value: float) -> float:
        if self.path is None:
            series = self._values.get(subject) or []
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT value FROM pythia_baselines WHERE subject=? "
                    "ORDER BY observed_at DESC LIMIT 200",
                    (subject,),
                ).fetchall()
            series = [float(row[0]) for row in rows]
        if len(series) < 2:
            return 0.0
        mean = sum(series) / len(series)
        var = sum((x - mean) ** 2 for x in series) / len(series)
        sd = math.sqrt(var) or 1.0
        return (value - mean) / sd

    def _connect(self) -> sqlite3.Connection:
        if self.path is None:
            raise RuntimeError("in-memory baseline store has no sqlite connection")
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn


def predict(subject: str, horizon: str, signals: dict[str, float], baselines: BaselineStore | None = None) -> Forecast:
    """Rule/heuristic v0. Runs off the voice turn (ADR-24)."""
    keys = list(signals)
    raw = sum(signals.values()) / max(len(signals), 1)
    store = baselines or BaselineStore()
    z = store.zscore(subject, raw)
    conf = max(0.15, min(0.85, 0.4 + abs(z) * 0.1))
    return Forecast(
        subject=subject,
        horizon=horizon,
        value=raw,
        confidence=conf,
        drivers=tuple(keys[:4]),
        provenance="pythia.rule.v0",
    )


def predict_threshold_event(
    subject: str,
    horizon: str,
    *,
    last_value: float,
    threshold: float,
    scale: float,
) -> Forecast:
    """Forecast the probability that the next value exceeds a threshold."""
    probability = 1.0 / (1.0 + math.exp(-(last_value - threshold) / max(1.0, scale)))
    return Forecast(
        subject=subject,
        horizon=horizon,
        value=last_value,
        confidence=max(0.01, min(0.99, probability)),
        drivers=("last_value", "threshold"),
        provenance="pythia.threshold.v0",
    )


def brier(forecasts: list[tuple[float, float]]) -> float:
    """forecasts: (confidence, outcome 0/1)."""
    if not forecasts:
        return 0.0
    return sum((p - o) ** 2 for p, o in forecasts) / len(forecasts)


def maybe_trigger(forecast: Forecast, *, ready: bool) -> dict[str, Any] | None:
    """SAM-076: high-confidence x high-impact becomes a follow-up, never blocks v2v."""
    if not ready:
        return {"kind": "follow_up", "forecast": forecast.as_artifact()}
    if forecast.confidence >= 0.75:
        return {"kind": "nudge", "forecast": forecast.as_artifact()}
    return None


class ForecastLedger:
    """Durable forecast/outcome pairs for off-path calibration."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pythia_forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    horizon TEXT NOT NULL,
                    value REAL NOT NULL,
                    confidence REAL NOT NULL,
                    drivers_json TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    outcome REAL,
                    resolved_at REAL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def record(self, forecast: Forecast) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO pythia_forecasts(
                    subject, horizon, value, confidence, drivers_json,
                    provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast.subject,
                    forecast.horizon,
                    forecast.value,
                    forecast.confidence,
                    json.dumps(list(forecast.drivers)),
                    forecast.provenance,
                    forecast.created_at,
                ),
            )
            return int(cur.lastrowid)

    async def record_async(self, forecast: Forecast) -> int:
        return await asyncio.to_thread(self.record, forecast)

    def resolve(self, forecast_id: int, outcome: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE pythia_forecasts SET outcome=?, resolved_at=? WHERE id=?",
                (max(0.0, min(1.0, float(outcome))), time.time(), forecast_id),
            )

    async def resolve_async(self, forecast_id: int, outcome: float) -> None:
        await asyncio.to_thread(self.resolve, forecast_id, outcome)

    def calibration(self, subject: str | None = None) -> tuple[int, float | None]:
        query = (
            "SELECT confidence, outcome FROM pythia_forecasts "
            "WHERE outcome IS NOT NULL"
        )
        params: tuple[Any, ...] = ()
        if subject:
            query += " AND subject=?"
            params = (subject,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        pairs = [(float(row["confidence"]), float(row["outcome"])) for row in rows]
        return len(pairs), brier(pairs) if pairs else None

    def calibration_candidate(
        self,
        *,
        subject: str,
        minimum_samples: int = 10,
        brier_threshold: float = 0.25,
    ) -> dict[str, Any] | None:
        count, score = self.calibration(subject)
        if score is None or count < minimum_samples or score <= brier_threshold:
            return None
        return {
            "kind": "skill_candidate",
            "skill_name": f"pythia_calibration:{subject}",
            "sample_count": count,
            "brier": score,
            "advisory_only": True,
        }
