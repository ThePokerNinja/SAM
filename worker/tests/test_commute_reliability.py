"""Owner commute call: full tools, greeting, standing callback, reminder, review link."""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from sam_worker.session import (
    allows_pack_switch,
    build_session,
    greeting_instructions,
    route_session_kind,
)
from sam_worker.standing import parse_standing_instruction
from sam_worker.tools.handlers import handle_named_tool
from sam_worker.tools.select import (
    calendar_action_for_utterance,
    select_tools_for_utterance,
    utterance_closes_proposal,
    utterance_opens_proposal,
)

_ROOM = "call-_+18318186191_x"
_WHEN = datetime(2026, 10, 6, 9, 2, tzinfo=ZoneInfo("America/Los_Angeles"))


def test_charles_working_stays_on_the_full_set() -> None:
    text = "do you know what Charles is working on right now?"
    assert route_session_kind(surface="phone", keyword=text, room_name=_ROOM) == "trading"
    assert not utterance_opens_proposal(text)
    names = select_tools_for_utterance(text)
    assert "charles_activity" in names


def test_harbor_dump_keeps_proposal_tools_and_trading_pack() -> None:
    dump = "Website for Harbor Izakaya with reservations and menu, this month."
    assert route_session_kind(surface="phone", keyword=dump, room_name=_ROOM) == "trading"
    assert utterance_opens_proposal(dump)
    names = select_tools_for_utterance(dump)
    assert "proposal_revise" in names
    assert "propose_calendar_change" not in names


def test_reminder_selects_calendar_and_notes() -> None:
    text = "set a reminder for tomorrow at noon and include the notes"
    assert calendar_action_for_utterance(text) == "create"
    names = select_tools_for_utterance(text)
    assert "propose_calendar_change" in names
    assert "capture_note" in names


def test_next_question_is_not_a_calendar_move() -> None:
    text = "Move to the next question."
    assert calendar_action_for_utterance(text) is None
    assert "propose_calendar_change" not in select_tools_for_utterance(text)
    assert (
        calendar_action_for_utterance("Move Samuel scheduling proof to Wednesday at four")
        == "update"
    )


def test_owner_can_leave_intake_builder_cannot() -> None:
    assert route_session_kind(
        surface="phone", keyword="Continue.", room_name=_ROOM, current_kind="trading"
    ) == "intake"
    assert route_session_kind(
        surface="phone",
        keyword="I don't wanna talk about Rainmaker anymore",
        room_name=_ROOM,
        current_kind="intake",
    ) == "trading"
    session = build_session(session_id="call-owner", surface="phone", room_name=_ROOM)
    assert session.activate_from_utterance("Continue.") is True
    assert session.kind == "intake"
    assert session.activate_from_utterance("back to trading") is True
    assert session.kind == "trading"
    assert allows_pack_switch("intake", "builder-eng-1") is False
    assert allows_pack_switch("intake", _ROOM) is True
    assert allows_pack_switch("intake") is False


def test_stop_repeating_does_not_close_a_proposal() -> None:
    assert utterance_opens_proposal("help me brainstorm a new concept")
    assert not utterance_closes_proposal("stop stop you're repeating")
    assert utterance_closes_proposal("this isn't a proposal")


def test_tuesday_commute_greeting_uses_the_clock_and_last_thread() -> None:
    text = greeting_instructions(
        "trading",
        now=_WHEN,
        prior_hook="hash security",
        last_opener="Monday opener",
        standing='When the owner says "you are the robot", respond: thanks, you\'re the man.',
    )
    low = text.lower()
    assert "how you can help" not in low
    assert "how can i help" not in low
    assert "tuesday" in low
    assert "office" in low
    assert "hash security" in low
    assert "monday opener" in low
    assert "robot" in low


def test_robot_callback_parses() -> None:
    line = parse_standing_instruction(
        "when I say you are the robot, say thanks, you're the man"
    )
    assert line is not None
    assert "you are the robot" in line
    assert "thanks, you're the man" in line


def test_text_the_link_stays_on_the_full_set() -> None:
    text = "text me the link"
    assert route_session_kind(surface="phone", keyword=text, room_name=_ROOM) == "trading"
    assert "text_me" in select_tools_for_utterance(text)
    emailed = "email this to me"
    assert route_session_kind(surface="phone", keyword=emailed, room_name=_ROOM) == "trading"
    assert "send_email" in select_tools_for_utterance(emailed)


def test_proposal_tool_speaks_the_review_url() -> None:
    class _Client:
        async def run_tool(self, name: str, args: dict | None = None) -> dict:
            return {"ok": True, "text": "Saved.", "engagementId": "eng-9"}

    spoken = asyncio.run(handle_named_tool(_Client(), "proposal_mark_estimate_ready", {}))
    assert "https://start.michaelstewman.com/?e=eng-9" in spoken
    assert "tap the bar" not in spoken.lower()
