"""Register Rainmaker rm_api tools on the shared ToolRegistry (SAM-035)."""

from __future__ import annotations

import asyncio
from typing import Any

from livekit.agents import RunContext

from .handlers import (
    handle_get_brief,
    handle_get_pulse,
    handle_get_research,
    handle_get_scans,
    handle_get_trades,
    handle_queue_research,
    handle_send_brief,
    handle_send_hero,
)
from .registry import ToolRegistry, ToolSpec


def register_rainmaker_tools(registry: ToolRegistry) -> None:
    """Add all Rainmaker command-surface tools. Call once when building the worker session."""

    registry.register(
        ToolSpec(
            name="get_scans",
            description=(
                "Get the latest Rainmaker scan picks (ticker symbols and any new tickers today). "
                "Use this whenever the user asks about scans, picks, watchlist, or what's on the board."
            ),
            read_only=True,
            requires_approval=False,
        ),
        _build_get_scans,
    )
    registry.register(
        ToolSpec(
            name="get_pulse",
            description=(
                "Get the current market pulse / morning bias (regime, lean, confidence). "
                "Use this for any question about the market read, mood, regime, or how the tape looks."
            ),
            read_only=True,
            requires_approval=False,
        ),
        _build_get_pulse,
    )
    registry.register(
        ToolSpec(
            name="get_trades",
            description=(
                "Get recent realized (closed) Rainmaker trades. "
                "Use this for questions about trades, positions, P/L, or recent performance."
            ),
            read_only=True,
            requires_approval=False,
        ),
        _build_get_trades,
    )
    registry.register(
        ToolSpec(
            name="get_research",
            description=(
                "Read the most recent Rainmaker research digest (completed research ideas + summaries). "
                "Use this when the user asks about research, the latest findings, or what's been researched."
            ),
            read_only=True,
            requires_approval=False,
        ),
        _build_get_research,
    )
    registry.register(
        ToolSpec(
            name="run_scan",
            description=(
                "Trigger a fresh Rainmaker scan now. Owner only. Use only when the owner explicitly "
                "asks to run, refresh, or re-run the scan. It starts the scan and returns immediately."
            ),
            read_only=False,
            requires_approval=True,
        ),
        _build_run_scan,
    )
    registry.register(
        ToolSpec(
            name="queue_research",
            description=(
                "Queue a Rainmaker research request on a topic or ticker. Owner only. Use when the owner "
                "asks you to research something. `topic` is what to research (a company, ticker, or question)."
            ),
            read_only=False,
            requires_approval=True,
        ),
        _build_queue_research,
    )
    registry.register(
        ToolSpec(
            name="get_brief",
            description=(
                "Read the owner's morning brief aloud (priorities, schedule, market line). "
                "Use when they ask for the brief, morning summary, or what's on today."
            ),
            read_only=True,
            requires_approval=False,
        ),
        _build_get_brief,
    )
    registry.register(
        ToolSpec(
            name="send_brief",
            description=(
                "Text the full morning brief to the owner's phone. Owner only. Use when they ask to "
                "text/send the brief, or want the full brief on their phone."
            ),
            read_only=False,
            requires_approval=True,
        ),
        _build_send_brief,
    )
    registry.register(
        ToolSpec(
            name="send_hero",
            description=(
                "Send the Samuel HERO character card image to the owner's phone via text. Owner only. "
                "Use when they ask for their hero card, character card, or stats card."
            ),
            read_only=False,
            requires_approval=True,
        ),
        _build_send_hero,
    )


def _build_get_scans(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def get_scans(context: RunContext) -> str:
        return await handle_get_scans(client, limit=5)

    return get_scans


def _build_get_pulse(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def get_pulse(context: RunContext) -> str:
        return await handle_get_pulse(client)

    return get_pulse


def _build_get_trades(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def get_trades(context: RunContext) -> str:
        return await handle_get_trades(client, status=None)

    return get_trades


def _build_get_research(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def get_research(context: RunContext) -> str:
        return await handle_get_research(client, limit=3)

    return get_research


def _build_run_scan(client: Any, _is_owner: Any, deps: dict[str, Any]):
    run_scan_bg = deps.get("run_scan_bg")

    async def run_scan(context: RunContext) -> str:
        if run_scan_bg is not None:
            asyncio.ensure_future(run_scan_bg(client))
        return (
            "Scan started - it takes about a minute. Ask me for the latest picks shortly "
            "and I'll read what it found."
        )

    return run_scan


def _build_queue_research(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def queue_research(context: RunContext, topic: str) -> str:
        return await handle_queue_research(client, topic)

    return queue_research


def _build_get_brief(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def get_brief(context: RunContext) -> str:
        return await handle_get_brief(client)

    return get_brief


def _build_send_brief(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def send_brief(context: RunContext) -> str:
        return await handle_send_brief(client)

    return send_brief


def _build_send_hero(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def send_hero(context: RunContext) -> str:
        return await handle_send_hero(client)

    return send_hero
