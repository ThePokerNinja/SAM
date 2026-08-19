"""Calendar tool handlers preserve machine references and spoken confirmation."""

from __future__ import annotations

import asyncio

from sam_worker.tools.handlers import (
    handle_commit_calendar_change,
    handle_get_calendar_events,
    handle_propose_calendar_change,
)
from sam_worker.tools.rainmaker import MockRainmakerClient


def test_read_includes_machine_event_reference() -> None:
    result = asyncio.run(
        handle_get_calendar_events(MockRainmakerClient(), days=7)
    )
    assert "Team sync" in result
    assert "[event_id=mock-event]" in result


def test_today_read_clamps_zero_days_to_one() -> None:
    seen: list[int] = []

    class Spy(MockRainmakerClient):
        async def get_calendar_events(self, days: int = 7) -> dict:
            seen.append(days)
            return await super().get_calendar_events(days)

    result = asyncio.run(handle_get_calendar_events(Spy(), days=0))
    assert seen == [1]
    assert "Team sync" in result


def test_proposal_reads_back_and_waits() -> None:
    result = asyncio.run(
        handle_propose_calendar_change(
            MockRainmakerClient(),
            session_id="call-1",
            action="create",
            summary="Coffee",
        )
    )
    assert "Say yes to confirm" in result
    assert "[proposal_id=mock-proposal]" in result


def test_commit_reports_created_event() -> None:
    result = asyncio.run(
        handle_commit_calendar_change(
            MockRainmakerClient(),
            session_id="call-1",
        )
    )
    assert "Booked Event" in result
