"""SAM-078 / Wave 8.2: token budget split and per-turn tool subset."""

from __future__ import annotations

from sam_worker.prompt_budget import (
    TARGET_PROMPT_TOKENS,
    all_rainmaker_specs,
    breakdown,
    estimate_tokens,
    samuel_instructions,
    specs_named,
)
from sam_worker.tools.select import (
    STUDIO_TOOLS,
    VOICE_TOOLS,
    filter_tools,
    select_tools_for_utterance,
)


def test_estimate_tokens_empty_is_zero() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1


def test_full_fourteen_dump_still_blows_the_target() -> None:
    """Attaching every tool every turn is the TPM killer; do not send that set."""
    budget = breakdown(system=samuel_instructions(), specs=all_rainmaker_specs())
    assert budget.tool_count == 14
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


def test_select_skips_studio_on_voice_path() -> None:
    names = select_tools_for_utterance("What's the market pulse looking like?")
    assert "get_pulse" in names
    assert not any(name in STUDIO_TOOLS for name in names)


def test_select_studio_only_when_asked() -> None:
    names = select_tools_for_utterance("List the studio campaign runs")
    assert set(STUDIO_TOOLS).issubset(set(names))


def test_select_pricing_and_stories_get_no_tools() -> None:
    assert select_tools_for_utterance("How much does Rainmaker cost?") == []
    assert select_tools_for_utterance("Tell me a short story about the market") == []


def test_filter_tools_preserves_requested_order() -> None:
    class _Tool:
        def __init__(self, name: str) -> None:
            self.__name__ = name

    tools = [_Tool("get_scans"), _Tool("get_pulse"), _Tool("get_brief")]
    filtered = filter_tools(tools, ["get_pulse", "get_scans"])
    assert [t.__name__ for t in filtered] == ["get_pulse", "get_scans"]


def test_voice_tool_count() -> None:
    assert len(VOICE_TOOLS) == 9
    assert len(STUDIO_TOOLS) == 5
