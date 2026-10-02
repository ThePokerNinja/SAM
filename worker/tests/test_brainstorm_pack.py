"""Platform 4.0 brainstorm session kind: pack routing + save_brainstorm handler."""

from __future__ import annotations

import asyncio

from sam_worker.packs.registry import PackRegistry
from sam_worker.session import build_session, pack_for_kind, route_session_kind
from sam_worker.tools.handlers import handle_save_brainstorm
from sam_worker.tools.rainmaker import MockRainmakerClient
from sam_worker.tools.select import select_tools_for_utterance


def test_brainstorm_routes_from_portal_and_phone_and_room_prefix() -> None:
    assert route_session_kind(surface="portal", keyword="Samuel, brainstorm with me") == "brainstorm"
    assert route_session_kind(surface="phone", keyword="let me think out loud for a sec", room_name="call-_+1555_abc") == "brainstorm"
    assert route_session_kind(surface="portal", room_name="brainstorm-owner-1") == "brainstorm"
    # Plain trading talk stays trading; "brainstorm" is not a substring trap for scans/picks.
    assert route_session_kind(surface="portal", keyword="what are today's picks") == "trading"
    assert pack_for_kind("brainstorm") == "brainstorm"


def test_brainstorm_session_activates_pack_and_scopes_tools() -> None:
    session = build_session(session_id="portal-owner", surface="portal")
    assert session.kind == "trading"
    assert session.activate_from_utterance("I want to brainstorm the Q4 plan") is True
    assert session.kind == "brainstorm" and session.pack == "brainstorm"
    reg = PackRegistry()
    pack = reg.get("brainstorm")
    assert pack.tools == ("save_brainstorm", "list_captures")
    assert "one_question_max" in pack.safety_rules
    assert "at most one clarifying question" in pack.persona_overlay
    assert reg.tools_for("brainstorm", ["get_pulse", "save_brainstorm", "capture_note", "list_captures"]) == [
        "save_brainstorm",
        "list_captures",
    ]
    # Owner can leave the pack the same way they leave any other.
    assert session.activate_from_utterance("back to trading") is True
    assert session.kind == "trading"


def test_select_tools_loads_save_brainstorm_on_done_and_brainstorm_words() -> None:
    assert "save_brainstorm" in select_tools_for_utterance("okay I'm done, save that brainstorm")
    assert "save_brainstorm" in select_tools_for_utterance("let me riff on the content engine")
    assert "save_brainstorm" not in select_tools_for_utterance("what is the pulse?")


def test_handle_save_brainstorm_posts_one_structured_call() -> None:
    class Spy(MockRainmakerClient):
        calls: list[tuple[str, dict]] = []

        async def run_tool(self, name, args=None):
            self.calls.append((name, dict(args or {})))
            return {"ok": True, "name": name, "text": "Saved brainstorm #ab12cd. It shows in the Morning inbox and tonight's digest."}

    spy = Spy()
    out = asyncio.run(
        handle_save_brainstorm(
            spy,
            title="  Q4 content engine ",
            decisions=["drafts only, never auto-post", " "],
            open_questions=[],
            next_actions=["review Thursday's draft"],
            notes="talked  through on the drive\nin two parts",
        )
    )
    assert out.startswith("Saved brainstorm #ab12cd")
    assert spy.calls == [
        (
            "save_brainstorm",
            {
                "title": "Q4 content engine",
                "decisions": ["drafts only, never auto-post"],
                "next_actions": ["review Thursday's draft"],
                "notes": "talked through on the drive in two parts",
            },
        )
    ]
    # Nothing to save -> no network call.
    spy.calls.clear()
    assert "Give me a title" in asyncio.run(handle_save_brainstorm(spy, title=""))
    assert spy.calls == []
