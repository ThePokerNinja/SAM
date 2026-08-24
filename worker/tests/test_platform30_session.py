from sam_worker.demo_cap import is_capped_room, should_hangup
from sam_worker.packs.registry import PackRegistry
from sam_worker.session import (
    BUILDER_OPENING,
    greeting_instructions,
    route_session_kind,
    should_speak_builder_opening,
)
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


def test_intake_pack_is_proposal_tools() -> None:
    names = PackRegistry().tools_for(
        "intake",
        ["capture_note", "grant_room", "place_call", "run_scan", "proposal_apply_summary"],
    )
    assert names == ["capture_note", "proposal_apply_summary"]


def test_centaur_idea_utterance_selects_tool() -> None:
    assert "centaur_idea" in select_tools_for_utterance("queue this idea tonight")