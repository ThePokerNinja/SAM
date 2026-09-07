from __future__ import annotations

import asyncio

from sam_worker.agent import first_builder_dump_id
from sam_worker.demo_cap import is_capped_room, should_hangup
from sam_worker.packs.registry import PackRegistry
from sam_worker.session import (
    BUILDER_OPENING,
    BUILDER_REASK,
    allows_pack_switch,
    allows_skill_approval_sms,
    build_session,
    greeting_instructions,
    is_owner_inbound_phone_call,
    route_session_kind,
    should_speak_builder_opening,
    should_use_builder_intake_path,
    should_use_phone_listen_first_intake,
)
from sam_worker.tools.rainmaker_registry import engagement_id_from_room
from sam_worker.tools.select import INTAKE_PACK_TOOLS, VOICE_INTAKE_LLM_TOOLS, select_tools_for_utterance


def test_owner_phone_call_starts_as_samuel_not_intake() -> None:
    assert is_owner_inbound_phone_call("call-_+15551212_abc")
    assert not is_owner_inbound_phone_call("samuel-dial-guest")
    assert route_session_kind(surface="phone", room_name="call-_+15551212_abc") == "trading"
    session = build_session(
        session_id="call-owner",
        surface="phone",
        room_name="call-_+15551212_abc",
    )
    assert session.kind == "trading"
    assert session.pack == "trading"


def test_owner_phone_call_uses_samuel_greet_not_builder_opening() -> None:
    assert not should_speak_builder_opening("call-_+15551212_abc", is_phone=True)
    assert should_speak_builder_opening("builder-abc", is_phone=True)
    trading = greeting_instructions("trading")
    assert "how you can help" in trading.lower()
    assert "proposal builder" not in trading.lower()
    assert "make real" in BUILDER_OPENING.lower()


def test_room_prefix_routes_moderator_and_intake() -> None:
    assert route_session_kind(surface="portal", room_name="mod-abc") == "moderator"
    assert route_session_kind(surface="portal", room_name="demo-xyz") == "intake"
    assert route_session_kind(surface="portal", room_name="intake-1") == "intake"
    assert route_session_kind(surface="portal", room_name="builder-abc") == "intake"
    assert route_session_kind(surface="phone", room_name="samuel-dial-abc") == "intake"


def test_phone_proposal_dump_routes_intake() -> None:
    dump = "Website for Harbor Izakaya with reservations and menu, this month."
    assert route_session_kind(surface="phone", keyword=dump, room_name="call-owner") == "intake"


def test_phone_talk_about_routes_intake_before_project_keyword() -> None:
    scoping = "Yeah. I wanna talk about"
    assert route_session_kind(surface="phone", keyword=scoping, room_name="call-owner") == "intake"


def test_demo_cap_hangup_rules() -> None:
    assert is_capped_room("demo-abc")
    assert is_capped_room("mod-xyz")
    assert is_capped_room("intake-1")
    assert not is_capped_room("builder-abc")
    assert not is_capped_room("demo-builder-eng-1")
    assert not is_capped_room("call-owner")
    assert should_hangup({"ok": False, "error": "http_409"})
    assert should_hangup({"ok": False, "error": "minutes_cap"})
    assert not should_hangup({"ok": True})
    assert not should_hangup({"ok": False, "error": "timeout"})


def test_builder_room_uses_spoken_opening() -> None:
    assert should_speak_builder_opening("builder-abc")
    assert not should_speak_builder_opening("call-_+15551212_abc", is_phone=True)
    assert not should_speak_builder_opening("demo-abc")
    assert not should_speak_builder_opening("sam-owner")
    assert should_use_builder_intake_path("builder-abc", "intake")
    assert should_use_phone_listen_first_intake("call-_+15551212_abc", "intake", is_phone=True)
    assert not should_use_builder_intake_path("call-_+15551212_abc", "intake", is_phone=True)
    assert not should_use_builder_intake_path("call-_+15551212_abc", "trading", is_phone=True)
    assert not should_use_builder_intake_path("sam-owner", "intake", is_phone=False)
    assert "Samuel" in BUILDER_OPENING
    assert "make real" in BUILDER_OPENING
    assert "what's the job" in BUILDER_REASK.lower()


def test_intake_pack_tool_set_is_closed() -> None:
    names = set(
        PackRegistry().tools_for(
            "intake",
            list(INTAKE_PACK_TOOLS) + ["run_command", "get_pulse"],
        )
    )
    assert names <= INTAKE_PACK_TOOLS


def test_voice_intake_llm_tools_omit_page_only_writers() -> None:
    assert "proposal_save_questions" in INTAKE_PACK_TOOLS
    assert "proposal_save_questions" not in VOICE_INTAKE_LLM_TOOLS
    assert "proposal_save_research" not in VOICE_INTAKE_LLM_TOOLS
    assert "proposal_apply_summary" in VOICE_INTAKE_LLM_TOOLS


def test_builder_greeting_is_not_the_portal_greeting() -> None:
    builder = greeting_instructions("intake")
    portal = greeting_instructions("trading")
    assert "samuel" in builder.lower()
    assert "how you can help" not in builder.lower()
    assert "how you can help" in portal.lower()
    assert "proposal builder" not in portal.lower()


def test_intake_overlay_is_listen_first() -> None:
    overlay = PackRegistry().get("intake").persona_overlay.lower()
    assert "listen first" in overlay
    assert "answer the last thing they said" in overlay
    assert "never repeat the same offer line twice" in overlay
    assert "event reset" in overlay


def test_intake_overlay_walks_gaps_and_confirms_filled_rows() -> None:
    overlay = PackRegistry().get("intake").persona_overlay.lower()
    assert "proposal_ask_gap" in overlay
    assert "want to change this, or leave it" in overlay
    assert "tiny jobs" not in overlay
    assert "proposal_save_research" not in overlay
    assert "phase 1 is understanding the job" in overlay
    assert "never repeat the same offer line twice" in overlay
    assert "tap the bar" in overlay


def test_first_builder_dump_skips_sync_and_portal() -> None:
    dump = "I need business cards."
    assert first_builder_dump_id("builder-eng-1", dump, already=False) == "eng-1"
    assert first_builder_dump_id("builder-eng-1", "[SYNC] wait", already=False) == ""
    assert first_builder_dump_id("builder-eng-1", dump, already=True) == ""
    assert first_builder_dump_id("sam-owner", dump, already=False) == ""


def test_builder_room_injects_engagement_id() -> None:
    assert engagement_id_from_room("builder-eng-abc") == "eng-abc"
    assert engagement_id_from_room("demo-builder-eng-xyz") == "eng-xyz"
    assert engagement_id_from_room("sam-owner") == ""


def test_intake_pack_is_proposal_tools() -> None:
    names = PackRegistry().tools_for(
        "intake",
        [
            "capture_note",
            "grant_room",
            "moderate_room",
            "place_call",
            "run_scan",
            "request_doctor",
            "text_me",
            "send_email",
            "proposal_apply_summary",
        ],
    )
    assert names == ["capture_note", "proposal_apply_summary"]
    assert not allows_pack_switch("intake")
    assert allows_pack_switch("trading")
    assert not allows_skill_approval_sms("trading", "builder-eng-1")
    assert not allows_skill_approval_sms("intake", "demo-builder-eng-1")
    assert allows_skill_approval_sms("intake", "demo-abc")
    assert allows_skill_approval_sms("intake", "samuel-dial-abc")
    assert allows_skill_approval_sms("trading")
    assert allows_skill_approval_sms("moderator", "mod-abc")


def test_builder_room_stays_intake_when_utterance_says_moderate() -> None:
    session = build_session(
        session_id="builder-eng-1",
        surface="portal",
        room_name="builder-eng-1",
    )
    assert session.kind == "intake"
    assert session.pack == "intake"
    assert not session.activate_from_utterance("Samuel, moderate this disagreement")
    assert session.kind == "intake"
    assert session.pack == "intake"
    assert not session.activate_from_utterance("go back to trading mode")
    assert session.kind == "intake"


def test_phone_owner_intake_turn_sequence_after_fragment_dump() -> None:
    """Three opener fragments + Harbor dump should stay on research/discovery, not estimate."""
    from sam_worker.builder_intake import run_builder_intake_turn

    class _PhoneClient:
        def __init__(self) -> None:
            self.tools: list[str] = []
            self._phase = 0

        async def get_intake_sync(self, engagement_id: str) -> dict:
            return {"ok": True, "engagementId": engagement_id, "complete": False, "gaps": [], "answers": []}

        async def run_tool(self, name: str, args: dict | None = None) -> dict:
            self.tools.append(name)
            if name == "proposal_apply_summary":
                return {
                    "ok": True,
                    "engagementId": "eng-phone-lab",
                    "text": "Got it — lining up research.",
                    "gap": {"field": "research", "question": "Hang on while I pull research."},
                }
            if name == "proposal_research":
                return {"ok": True, "text": "Research attached."}
            if name == "proposal_ask_gap":
                return {
                    "ok": True,
                    "engagementId": "eng-phone-lab",
                    "text": "What problem is Harbor Izakaya solving?",
                    "gap": {
                        "field": "discovery",
                        "questionId": "problem-statement",
                        "question": "What problem is Harbor Izakaya solving?",
                    },
                    "complete": False,
                }
            return {"ok": True, "text": "Next?"}

    client = _PhoneClient()
    for fragment in (
        "Yeah. I wanna talk about",
        "digital service project.",
        "a mobile website for our izakaya with reservations and menu.",
    ):
        spoken, tools = asyncio.run(
            run_builder_intake_turn(client, engagement_id="", text=fragment)
        )
        assert "One second" not in (spoken or "")
        assert "putting the estimate up" not in (spoken or "").lower()

    dump = 'Website for "Harbor Izakaya" with reservations and menu, this month.'
    spoken, tools = asyncio.run(
        run_builder_intake_turn(client, engagement_id="eng-phone-lab", text=dump)
    )
    assert "proposal_apply_summary" in tools or "proposal_ask_gap" in tools
    assert "hang on" not in (spoken or "").lower()
    assert "putting the estimate up" not in (spoken or "").lower()
    assert "problem" in (spoken or "").lower() or "what" in (spoken or "").lower()