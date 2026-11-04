"""2026-11-03 commute call: "make a note" became nine calendar proposals and no saved note.

The utterances below are the phone's fragments from that call.
"""

from sam_worker.tools.select import (
    calendar_action_for_utterance,
    is_calendar_confirm,
    select_tools_for_utterance,
)

NOTE_ABOUT_EXITS = "Make a note. The stops are too low and the limits are too high, they should be at support and resistance."


def test_a_trading_note_goes_to_the_trading_discussion_not_the_calendar():
    tools = select_tools_for_utterance(NOTE_ABOUT_EXITS)
    assert tools[0] == "save_trading_discussion" and "capture_note" in tools
    assert "propose_calendar_change" not in tools and "stage_trade" not in tools
    assert calendar_action_for_utterance(NOTE_ABOUT_EXITS) is None


def test_a_plain_note_is_a_capture():
    tools = select_tools_for_utterance("Can you make a note to change the oil this weekend")
    assert tools[0] == "capture_note" and "propose_calendar_change" not in tools


def test_a_note_that_names_the_calendar_still_reaches_the_calendar():
    assert calendar_action_for_utterance("Make a note on my calendar to move the dentist") == "update"


def test_yeah_so_is_the_start_of_a_sentence_not_a_yes():
    assert is_calendar_confirm("Yeah. So") is False
    assert is_calendar_confirm("Yeah") is True


def test_timing_ideas_are_saved_not_staged():
    for said in ("Let's make the buy immediately", "Let's not wait to get into it"):
        tools = select_tools_for_utterance(said)
        assert "save_trading_discussion" in tools and "stage_trade" not in tools, said


def test_a_named_buy_still_reaches_staging():
    assert "stage_trade" in select_tools_for_utterance("buy EVGO at the open")
