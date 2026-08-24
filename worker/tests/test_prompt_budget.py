"""SAM-078 / Wave 8.2: token budget split and per-turn tool subset."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sam_worker.prompt_budget import (
    TARGET_PROMPT_TOKENS,
    all_rainmaker_specs,
    breakdown,
    estimate_tokens,
    samuel_instructions,
    specs_named,
    volatile_clock_context,
)
from sam_worker.tools.select import (
    STUDIO_TOOLS,
    VOICE_TOOLS,
    calendar_action_for_utterance,
    filter_tools,
    is_calendar_confirm,
    select_tools_for_utterance,
)


def test_estimate_tokens_empty_is_zero() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1


def test_system_prefix_is_stable_and_clock_is_separate() -> None:
    first = samuel_instructions()
    second = samuel_instructions()
    assert first == second
    assert "Today is " not in first
    clock = volatile_clock_context(
        now=datetime(2026, 8, 19, 11, 12, tzinfo=ZoneInfo("America/Los_Angeles"))
    )
    assert "Today is Wednesday, August 19, 2026" in clock


def test_full_tool_dump_still_blows_the_target() -> None:
    """Attaching every tool every turn is the TPM killer; do not send that set."""
    budget = breakdown(system=samuel_instructions(), specs=all_rainmaker_specs())
    assert budget.tool_count == 46
    assert budget.tool_schema_tokens > 400
    assert budget.total_tokens > TARGET_PROMPT_TOKENS


def test_typical_unrouted_turn_fits_target() -> None:
    names = select_tools_for_utterance("How much does Rainmaker cost per month?")
    assert names == []
    budget = breakdown(
        system=samuel_instructions(),
        specs=specs_named(names),
        history=(
            "user: hey sam",
            "assistant: I'm here.",
            "user: How much does Rainmaker cost per month?",
        ),
    )
    assert budget.total_tokens <= TARGET_PROMPT_TOKENS
    assert budget.under_target is True


def test_cache_aware_budget_excludes_only_stable_prefix(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_TPM_BUDGET", "12000")
    system = samuel_instructions()
    specs = specs_named(["get_calendar_events", "propose_calendar_change"])
    uncached = breakdown(system=system, specs=specs, history=("user: hello",))
    cached = breakdown(
        system=system,
        specs=specs,
        history=("user: hello",),
        cached_prefix_tokens=uncached.system_tokens + uncached.tool_schema_tokens,
    )
    assert cached.tpm_budget == 12000
    assert cached.billable_prompt_tokens == cached.history_tokens
    assert cached.cache_savings_tokens > 0
    assert (
        cached.turns_per_minute_at_tpm_budget
        > uncached.turns_per_minute_at_tpm_budget
    )


def test_select_skips_studio_on_voice_path() -> None:
    names = select_tools_for_utterance("What's the market pulse looking like?")
    assert "get_pulse" in names
    assert not any(name in STUDIO_TOOLS for name in names)


def test_select_studio_only_when_asked() -> None:
    names = select_tools_for_utterance("List the studio campaign runs")
    assert set(STUDIO_TOOLS).issubset(set(names))


def test_select_pricing_and_stories_get_no_tools() -> None:
    assert select_tools_for_utterance("How much does Rainmaker cost?") == []
    assert select_tools_for_utterance("Tell me a short story about the market") == [
        "run_command"
    ]


def test_select_calendar_proposal_then_confirmation() -> None:
    proposal_names = select_tools_for_utterance(
        "Book a dentist appointment tomorrow at three"
    )
    assert proposal_names == ["propose_calendar_change", "run_command"]

    confirm_names = select_tools_for_utterance("Yes, confirm it")
    assert confirm_names == ["commit_calendar_change", "run_command"]
    assert select_tools_for_utterance("Yes, book it") == [
        "commit_calendar_change",
        "run_command",
    ]
    assert select_tools_for_utterance("Yes or no?") == ["run_command"]
    assert select_tools_for_utterance(
        "Yeah. I wanna book a fifteen minute appointment tomorrow at three"
    ) == ["propose_calendar_change", "run_command"]
    assert is_calendar_confirm("Yes.")
    assert is_calendar_confirm("Yes, book it")
    assert not is_calendar_confirm("Yes or no?")
    assert not is_calendar_confirm(
        "Yeah. I wanna book a fifteen minute appointment tomorrow"
    )


def test_add_another_appointment_selects_calendar_proposal() -> None:
    assert select_tools_for_utterance("add another appointment") == [
        "propose_calendar_change",
        "run_command",
    ]


def test_select_move_without_calendar_noun_and_commit_only_confirmation() -> None:
    move_names = select_tools_for_utterance(
        "Move Samuel scheduling proof to Wednesday at four"
    )
    assert move_names == ["propose_calendar_change", "run_command"]
    assert (
        calendar_action_for_utterance(
            "Move Samuel scheduling proof to Wednesday at four"
        )
        == "update"
    )
    assert calendar_action_for_utterance("Cancel dentist tomorrow") == "cancel"
    assert calendar_action_for_utterance("Book coffee tomorrow") == "create"

    confirm_names = select_tools_for_utterance(
        "I confirm the calendar change now"
    )
    assert confirm_names == ["commit_calendar_change", "run_command"]


def test_schedule_question_selects_read_instead_of_create() -> None:
    assert select_tools_for_utterance(
        "What is on my schedule today?"
    ) == ["get_calendar_events", "run_command"]
    assert select_tools_for_utterance(
        "Check my calendar for upcoming meetings"
    ) == ["get_calendar_events", "run_command"]
    assert select_tools_for_utterance(
        "My schedule today"
    ) == ["get_calendar_events", "run_command"]
    assert select_tools_for_utterance(
        "Schedule a meeting tomorrow at noon"
    ) == ["propose_calendar_change", "run_command"]
    assert select_tools_for_utterance(
        "Can you add an event to my calendar tomorrow?"
    ) == ["propose_calendar_change", "run_command"]
    assert calendar_action_for_utterance(
        "Edit my calendar and move the dentist appointment"
    ) == "update"


def test_filter_tools_preserves_requested_order() -> None:
    class _Tool:
        def __init__(self, name: str) -> None:
            self.__name__ = name

    tools = [_Tool("get_scans"), _Tool("get_pulse"), _Tool("get_brief")]
    filtered = filter_tools(tools, ["get_pulse", "get_scans"])
    assert [t.__name__ for t in filtered] == ["get_pulse", "get_scans"]


def test_voice_tool_count() -> None:
    assert len(VOICE_TOOLS) == 37
    assert len(STUDIO_TOOLS) == 5


def test_select_call_cathy_loads_reach_not_trading_call() -> None:
    assert "reach" in select_tools_for_utterance("call Cathy")
    assert "reach" in select_tools_for_utterance("can you call her")
    assert "reach" not in select_tools_for_utterance("NVDA call")
