"""Tests for per-turn latency instrumentation + the bench latency-profile analyzer (scaffold)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sam_worker.latency import TurnProfile, read_profiles, write_profile
from sam_worker.bench.latency_profile import (
    DEFAULT_TIERED_TARGETS,
    analyze,
    classify_tier,
    stage_percentiles,
)


def _profile(sid: str, eou: float, ttft: float, ttfb: float, **extra) -> TurnProfile:
    return TurnProfile(speech_id=sid, eou_ms=eou, llm_ttft_ms=ttft, tts_ttfb_ms=ttfb, **extra)


def test_turn_profile_v2v_and_serialize() -> None:
    p = _profile("s1", 400.0, 130.0, 170.0, stt_ms=120.0, barge_in_ms=200.0)
    assert p.v2v_ready() is True
    assert p.v2v_ms() == 700.0
    d = p.to_dict()
    assert d["speech_id"] == "s1"
    assert d["v2v_ms"] == 700.0
    assert d["stt_ms"] == 120.0
    assert d["barge_in_ms"] == 200.0


def test_v2v_not_ready_when_missing_stage() -> None:
    p = TurnProfile(speech_id="s2", eou_ms=400.0, llm_ttft_ms=130.0)  # no tts
    assert p.v2v_ready() is False
    assert p.to_dict()["v2v_ms"] is None


def test_jsonl_round_trip_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAM_LATENCY_LOG", "1")
    dest = tmp_path / "lat.jsonl"
    assert write_profile(_profile("a", 400, 130, 170), path=dest) is True
    assert write_profile(_profile("b", 500, 140, 180), path=dest) is True
    rows = read_profiles(dest)
    assert len(rows) == 2
    assert {r["speech_id"] for r in rows} == {"a", "b"}
    assert rows[0]["v2v_ms"] == 700.0


def test_jsonl_noop_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAM_LATENCY_LOG", raising=False)
    dest = tmp_path / "off.jsonl"
    assert write_profile(_profile("a", 400, 130, 170), path=dest) is False
    assert read_profiles(dest) == []


def test_stage_percentiles_skip_missing() -> None:
    rows = [
        _profile("a", 400, 130, 170, stt_ms=100).to_dict(),
        _profile("b", 600, 150, 190, stt_ms=200).to_dict(),
    ]
    summary = stage_percentiles(rows)
    assert summary["eou_ms"]["p50"] in (400.0, 600.0)
    assert summary["stt_ms"]["n"] == 2.0
    # barge_in never populated -> not present.
    assert "barge_in_ms" not in summary


def test_tier_classification_industry_leading() -> None:
    # v2v 580ms across the board, barge-in well under 150ms.
    rows = [_profile(f"s{i}", 300, 130, 150, barge_in_ms=120).to_dict() for i in range(10)]
    out = classify_tier(rows)
    assert out["tier"] == "industry_leading"
    assert out["v2v_p50_ms"] == 580.0


def test_tier_classification_premium() -> None:
    rows = [_profile(f"s{i}", 450, 130, 170, barge_in_ms=200).to_dict() for i in range(10)]
    out = classify_tier(rows)  # v2v 750ms -> Premium, not Industry-Leading
    assert out["tier"] == "premium"
    assert out["per_tier"]["premium"] is True
    assert out["per_tier"]["industry_leading"] is False


def test_tier_classification_misses_premium_at_current_latency() -> None:
    # Current measured ~1091ms p50 -> only Minimum Enterprise at best (p95 may still fail).
    rows = [_profile(f"s{i}", 741, 180, 170).to_dict() for i in range(10)]  # 1091ms
    out = classify_tier(rows)
    assert out["per_tier"]["premium"] is False


def test_barge_in_failure_demotes_tier() -> None:
    # Fast v2v but slow barge-in must not earn Premium.
    rows = [_profile(f"s{i}", 450, 130, 170, barge_in_ms=600).to_dict() for i in range(10)]
    out = classify_tier(rows)
    assert out["per_tier"]["premium"] is False


def test_analyze_shape_and_defaults_match() -> None:
    rows = [_profile(f"s{i}", 450, 130, 170).to_dict() for i in range(5)]
    out = analyze(rows, DEFAULT_TIERED_TARGETS)
    assert out["turns"] == 5
    assert "stages" in out and "classification" in out
    assert out["classification"]["tier"] in {"premium", "industry_leading", "minimum_enterprise", "none"}
