from __future__ import annotations

from dataclasses import dataclass

from sam_worker.continuity import (
    build_rolling_summary,
    build_thread_summary_text,
    brief_from_thread_summary,
    effective_history_token_cap,
    engagement_fields_for_context,
    extract_open_loops,
)
from sam_worker.demo_cap import is_capped_room


@dataclass
class _Settings:
    history_token_cap: int = 250
    owner_history_token_cap: int = 6000


def test_guest_demo_room_keeps_tight_history_cap() -> None:
    settings = _Settings()
    assert effective_history_token_cap(
        settings, is_owner=True, room_name="demo-abc"
    ) == 250
    assert is_capped_room("demo-abc")


def test_owner_builder_room_gets_long_history_cap() -> None:
    settings = _Settings()
    assert effective_history_token_cap(
        settings, is_owner=True, room_name="demo-builder-eng-1"
    ) == 6000


def test_rolling_summary_preserves_opening_dump() -> None:
    turns = [
        ("user", "We need a marketing site for a dental clinic with booking and SEO."),
        ("assistant", "Got it."),
        ("user", "Budget is forty thousand."),
        ("assistant", "Noted."),
    ]
    summary = build_rolling_summary(turns)
    assert "dental clinic" in summary
    assert "Budget" in summary


def test_thread_summary_includes_engagement_and_open_loops() -> None:
    turns = [
        ("user", "Let's follow up on the proposal builder tomorrow."),
        ("assistant", "Will do."),
    ]
    text = build_thread_summary_text(
        turns, engagement_id="eng-123", room_name="builder-eng-123"
    )
    assert "eng-123" in text
    assert extract_open_loops(turns)


def test_brief_from_thread_summary_merges_builder_context() -> None:
    brief = brief_from_thread_summary(
        {"summary": "Yesterday we scoped a dental site.", "openLoops": ["Send SOW"]},
        builder_context="client=Smile Studio; stage=proposal",
    )
    rendered = brief.as_prompt(token_budget=800)
    assert "Yesterday we scoped" in rendered
    assert "Smile Studio" in rendered
    assert "Open loops" in rendered


def test_engagement_fields_for_context() -> None:
    text = engagement_fields_for_context(
        {
            "client_name": "Acme",
            "project_name": "Website",
            "stage": "proposal",
            "answers": {"summary": "Full rebuild"},
        }
    )
    assert "Acme" in text
    assert "Full rebuild" in text
