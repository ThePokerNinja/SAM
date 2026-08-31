"""Unit tests for health payload, burst alerts, skill gaps, outbound allowlist."""

from __future__ import annotations

from types import SimpleNamespace

from sam_worker.alerts import BurstTracker, GROQ_429
from sam_worker.health import health_payload
from sam_worker.outbound import (
    can_dial,
    classify_outbound_first_speech,
    decode_outbound_metadata,
    encode_outbound_metadata,
    is_outbound_dial_room,
    normalize_e164,
    pick_outbound_metadata,
    sip_participant_is_answered,
    take_pending_script,
    wait_for_outbound_answer,
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


def test_resolve_brain_openai_canonical_when_both_keys() -> None:
    from sam_worker.config import Settings, resolve_brain

    s = Settings(
        sam_brain="",
        openai_api_key="sk-openai",
        groq_api_key="gsk_groq",
    )
    assert resolve_brain(s) == "openai"

    s_explicit = Settings(
        sam_brain="groq",
        openai_api_key="sk-openai",
        groq_api_key="gsk_groq",
    )
    assert resolve_brain(s_explicit) == "groq"


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
        spoken="Hi Cathy, this is Samuel.",
        notify_owner=True,
    )
    meta = decode_outbound_metadata(raw)
    assert meta["kind"] == "outbound_guest"
    assert meta["guest_name"] == "Cathy Arines"
    assert "Michael" in meta["brief"]
    assert meta["spoken"].startswith("Hi Cathy")
    assert meta["notify_owner"] is True
    assert is_outbound_dial_room("samuel-dial-abc")
    assert not is_outbound_dial_room("call-abc")
    assert pick_outbound_metadata("", raw) == raw
    assert pick_outbound_metadata("  ", "") == ""


def test_outbound_answer_ignores_ringing() -> None:
    ringing = SimpleNamespace(attributes={"sip.callStatus": "ringing"})
    active = SimpleNamespace(attributes={"sip.callStatus": "active"})
    assert sip_participant_is_answered(ringing) is False
    assert sip_participant_is_answered(active) is True


def test_wait_for_outbound_answer_flips_from_ringing() -> None:
    import asyncio

    room = SimpleNamespace(
        remote_participants={"sip": SimpleNamespace(attributes={"sip.callStatus": "ringing"})}
    )

    async def _run() -> bool:
        async def _answer() -> None:
            await asyncio.sleep(0.05)
            room.remote_participants["sip"].attributes["sip.callStatus"] = "active"

        asyncio.create_task(_answer())
        return await wait_for_outbound_answer(room, timeout_s=1.0)

    assert asyncio.run(_run()) is True


def test_outbound_script_waits_for_human_hello() -> None:
    state = {"spoken": "Hi Cathy, this is Samuel.", "delivered": False}
    assert classify_outbound_first_speech("Hello?") == "human"
    assert classify_outbound_first_speech("You called me.") == "human"
    assert take_pending_script(state, "Hello?") == "Hi Cathy, this is Samuel."
    assert state["delivered"] is True
    assert take_pending_script(state, "You called me.") is None


CATHY_SCRIPT = (
    "Hi Cathy, this is Samuel. Michael asked me to call you. He wanted you to hear "
    "that he loves you, that he is grateful you are his, and that he is thinking of you. "
    "Song of Solomon 2:16. My beloved is mine, and I am his. That is from him. "
    "Do you want to send him a short message back?"
)


def test_cathy_last_call_replay_delivers_script_on_hello() -> None:
    """Replay of samuel-dial-17e6ce1849 without placing another call."""
    state = {"spoken": CATHY_SCRIPT, "delivered": False}
    # SIP went active ~4s in last time. That must not consume the script.
    assert state["delivered"] is False
    assert take_pending_script(state, "") is None
    assert (
        take_pending_script(state, "Your call has been forwarded to voice mail.") == ""
    )
    assert (
        take_pending_script(state, "The person you're trying to reach is not available.")
        == ""
    )
    assert take_pending_script(state, "At the tone,") == ""
    spoken = take_pending_script(state, "Hello?")
    assert spoken == CATHY_SCRIPT
    assert "Song of Solomon 2:16" in spoken
    assert "My beloved is mine, and I am his." in spoken
    assert take_pending_script(state, "You called me.") is None
    assert take_pending_script(state, "I'm good.") is None


def test_llm_node_speaks_cathy_script_instead_of_improv() -> None:
    import asyncio

    from livekit.agents import ChatContext

    from sam_worker.router import FastIntentRouter, RoutedSamuelAgent

    async def direct(_decision):
        raise AssertionError("Cathy opener must not hit the LLM")

    async def publish(_command):
        return None

    agent = RoutedSamuelAgent(
        router=FastIntentRouter(),
        direct_execute=direct,
        publish_command=publish,
        instructions="test",
    )
    state = {"spoken": CATHY_SCRIPT, "delivered": False}
    agent._pending_override = take_pending_script(state, "Hello?")
    context = ChatContext.empty()
    context.add_message(role="user", content="Hello?")
    result = asyncio.run(agent.llm_node(context, [], None))
    assert result == CATHY_SCRIPT
    assert agent._pending_override is None


def test_outbound_script_holds_through_voicemail() -> None:
    state = {"spoken": "Hi Cathy, this is Samuel.", "delivered": False}
    assert classify_outbound_first_speech("Your call has been forwarded to voice mail.") == (
        "voicemail"
    )
    assert take_pending_script(state, "Your call has been forwarded to voice mail.") == ""
    assert state["delivered"] is False
    assert take_pending_script(state, "Hello?") == "Hi Cathy, this is Samuel."
    assert state["delivered"] is True
