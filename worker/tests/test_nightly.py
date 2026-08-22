"""SAM-075: the nightly Pythia calibration is scheduled and it notifies the owner."""

from __future__ import annotations

from datetime import datetime, timezone

from sam_worker.bench.pythia_nightly import run
from sam_worker.nightly import nightly_enabled, nightly_hour_utc, seconds_until
from sam_worker.pythia import Forecast, ForecastLedger


def _seed_badly_calibrated(path, subject: str, samples: int = 12) -> None:
    """Confident forecasts that all missed: Brier ~0.81, well over the 0.25 gate."""
    ledger = ForecastLedger(path)
    for _ in range(samples):
        forecast_id = ledger.record(
            Forecast(
                subject=subject,
                horizon="next_turn",
                value=1.0,
                confidence=0.9,
                drivers=("test",),
                provenance="unit_test",
            )
        )
        ledger.resolve(forecast_id, 0.0)


def test_seconds_until_targets_tomorrow_when_hour_has_passed() -> None:
    now = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)
    assert seconds_until(9, now=now) == 23 * 3600
    assert seconds_until(11, now=now) == 3600


def test_schedule_defaults_and_env_overrides(monkeypatch) -> None:
    monkeypatch.delenv("SAM_NIGHTLY_HOUR_UTC", raising=False)
    monkeypatch.delenv("SAM_NIGHTLY_ENABLED", raising=False)
    assert nightly_hour_utc() == 9
    assert nightly_enabled() is True
    monkeypatch.setenv("SAM_NIGHTLY_HOUR_UTC", "3")
    monkeypatch.setenv("SAM_NIGHTLY_ENABLED", "0")
    assert nightly_hour_utc() == 3
    assert nightly_enabled() is False


def test_empty_ledger_emits_nothing(tmp_path) -> None:
    result = run(tmp_path / "sam_memory.db", notify=None)
    assert result == {"ok": True, "emitted": False, "samples": 0, "brier": None}


def test_bad_calibration_notifies_the_owner_once(tmp_path) -> None:
    db = tmp_path / "sam_memory.db"
    subject = "next_turn_latency_over_800"
    _seed_badly_calibrated(db, subject)
    calls: list[tuple[str, str]] = []

    def notify(candidate_id: str, summary: str) -> dict:
        calls.append((candidate_id, summary))
        return {"ok": True, "code": "AB12"}

    result = run(db, subject, notify=notify)
    assert result["emitted"] is True
    assert result["notified"] is True
    assert len(calls) == 1

    # A standing miscalibration must not text the owner every night.
    repeat = run(db, subject, notify=notify)
    assert repeat["emitted"] is True
    assert repeat["notified"] is False
    assert len(calls) == 1


def test_notify_failure_still_records_the_candidate(tmp_path) -> None:
    db = tmp_path / "sam_memory.db"
    subject = "next_turn_latency_over_800"
    _seed_badly_calibrated(db, subject)

    def notify(candidate_id: str, summary: str) -> dict:
        raise RuntimeError("rm_api unreachable")

    result = run(db, subject, notify=notify)
    assert result["emitted"] is True
    assert result["notified"] is False
