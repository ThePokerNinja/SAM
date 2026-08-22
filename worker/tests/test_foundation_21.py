"""Unit tests for health payload, burst alerts, skill gaps, outbound allowlist."""

from __future__ import annotations

from sam_worker.alerts import BurstTracker, GROQ_429
from sam_worker.health import health_payload
from sam_worker.outbound import (
    can_dial,
    decode_outbound_metadata,
    encode_outbound_metadata,
    is_outbound_dial_room,
    normalize_e164,
)
from sam_worker.session import route_session_kind
from sam_worker.skillbuilder.advisory import run_advisory
from sam_worker.skillbuilder.gap import candidate_from_latency, candidate_from_pythia_brier
from sam_worker.skillbuilder.runtime import SkillBuilderRuntime
from sam_worker.skillbuilder.scoring import evaluate_candidate


def test_health_payload_ok(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    monkeypatch.setenv("SAM_BRAIN", "groq")
    payload = health_payload()
    assert payload["ok"] is True
    assert payload["service"] == "sam-agent"
    assert payload["git"] == "abc123"
    assert payload["brain"] == "groq"


def test_burst_tracker_fires_once() -> None:
    tracker = BurstTracker(window_s=60, threshold=3)
    assert tracker.observe(1.0, is_match=True) is False
    assert tracker.observe(2.0, is_match=True) is False
    assert tracker.observe(3.0, is_match=True) is True
    assert tracker.observe(4.0, is_match=True) is False
    assert GROQ_429 == "groq_429_burst"


def test_latency_candidate_gates(tmp_path) -> None:
    candidate = candidate_from_latency("room-1", v2v_p50_ms=980)
    assert candidate is not None
    evaluate_candidate(candidate)
    runtime = SkillBuilderRuntime(tmp_path / "skills.db")
    run_advisory(runtime, candidate, reason=candidate.problem_detected)
    assert candidate.gates.approved_for_adoption is True


def test_no_candidate_under_threshold() -> None:
    assert candidate_from_latency("room-1", v2v_p50_ms=600) is None


def test_pythia_candidate_shape() -> None:
    candidate = candidate_from_pythia_brier("next_turn_latency_over_800", sample_count=20, brier=0.4)
    evaluate_candidate(candidate)
    assert candidate.skill_name.startswith("pythia_calibration")


def test_staging_room_routes_skillbuilder() -> None:
    assert (
        route_session_kind(surface="portal", room_name="staging-latency") == "skillbuilder"
    )


def test_outbound_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("SAM_SIP_OUTBOUND_ALLOWED", "+15551212")
    monkeypatch.delenv("SAM_SIP_OWNER_NUMBERS", raising=False)
    monkeypatch.delenv("SAM_SIP_OUTBOUND_TRUNK_ID", raising=False)
    ok, reason = can_dial("+15551212")
    assert ok is False
    assert reason == "outbound_not_configured"
    assert normalize_e164("5551212345") == "+15551212345"
    blocked, why = can_dial("+19995551212")
    assert blocked is False
    assert why == "number_not_allowlisted"


def test_outbound_room_metadata_roundtrip() -> None:
    raw = encode_outbound_metadata(
        brief="Say hello from Michael.",
        guest_name="Cathy Arines",
        notify_owner=True,
    )
    meta = decode_outbound_metadata(raw)
    assert meta["kind"] == "outbound_guest"
    assert meta["guest_name"] == "Cathy Arines"
    assert "Michael" in meta["brief"]
    assert meta["notify_owner"] is True
    assert is_outbound_dial_room("samuel-dial-abc")
    assert not is_outbound_dial_room("call-abc")
