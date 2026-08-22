from sam_worker.demo_cap import is_capped_room, should_hangup
from sam_worker.packs.registry import PackRegistry
from sam_worker.session import route_session_kind
from sam_worker.tools.select import select_tools_for_utterance


def test_room_prefix_routes_moderator_and_intake() -> None:
    assert route_session_kind(surface="portal", room_name="mod-abc") == "moderator"
    assert route_session_kind(surface="portal", room_name="demo-xyz") == "intake"
    assert route_session_kind(surface="portal", room_name="intake-1") == "intake"
    assert route_session_kind(surface="phone", room_name="samuel-dial-abc") == "intake"


def test_demo_cap_hangup_rules() -> None:
    assert is_capped_room("demo-abc")
    assert is_capped_room("mod-xyz")
    assert not is_capped_room("call-owner")
    assert should_hangup({"ok": False, "error": "http_409"})
    assert should_hangup({"ok": False, "error": "minutes_cap"})
    assert not should_hangup({"ok": True})
    assert not should_hangup({"ok": False, "error": "timeout"})


def test_intake_pack_is_capture_note_only() -> None:
    names = PackRegistry().tools_for("intake", ["capture_note", "grant_room", "place_call", "run_scan"])
    assert names == ["capture_note"]


def test_centaur_idea_utterance_selects_tool() -> None:
    assert "centaur_idea" in select_tools_for_utterance("queue this idea tonight")