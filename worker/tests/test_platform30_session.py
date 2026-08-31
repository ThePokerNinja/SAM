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
    route_session_kind,
    should_speak_builder_opening,
)
from sam_worker.tools.rainmaker_registry import engagement_id_from_room
from sam_worker.tools.select import select_tools_for_utterance


def test_room_prefix_routes_moderator_and_intake() -> None:
    assert route_session_kind(surface="portal", room_name="mod-abc") == "moderator"
    assert route_session_kind(surface="portal", room_name="demo-xyz") == "intake"
    assert route_session_kind(surface="portal", room_name="intake-1") == "intake"
    assert route_session_kind(surface="portal", room_name="builder-abc") == "intake"
    assert route_session_kind(surface="phone", room_name="samuel-dial-abc") == "intake"


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
    assert not should_speak_builder_opening("demo-abc")
    assert not should_speak_builder_opening("sam-owner")
    assert "Samuel" in BUILDER_OPENING
    assert "make real" in BUILDER_OPENING
    assert "what's the job" in BUILDER_REASK.lower()


def test_builder_greeting_is_not_the_portal_greeting() -> None:
    builder = greeting_instructions("intake")
    portal = greeting_instructions("trading")
    assert "proposal builder" in builder.lower()
    assert "how you can help" not in builder.lower()
    assert "how you can help" in portal.lower()
    assert "proposal builder" not in portal.lower()


def test_intake_overlay_stays_collaborative() -> None:
    overlay = PackRegistry().get("intake").persona_overlay.lower()
    assert "few minutes" in overlay
    assert "how their day" in overlay


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


def test_intake_overlay_walks_gaps_and_confirms_filled_rows() -> None:
    overlay = PackRegistry().get("intake").persona_overlay.lower()
    assert "proposal_ask_gap" in overlay
    assert "want to change this, or leave it" in overlay
    assert "tiny jobs" not in overlay
    assert "proposal_save_research" not in overlay
    assert "do not discuss hours-trim" in overlay
    assert "email" in overlay and "sow" in overlay
    assert "tap the bar" in overlay


def test_intake_overlay_names_three_sections() -> None:
    overlay = PackRegistry().get("intake").persona_overlay.lower()
    assert "research" in overlay
    assert "discovery" in overlay
    assert "tap the bar" in overlay
    assert "proposal_apply_summary" in overlay


def test_centaur_idea_utterance_selects_tool() -> None:
    assert "centaur_idea" in select_tools_for_utterance("queue this idea tonight")