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
    handle_list_studio_runs,
    handle_make_studio_deliverable,
    handle_queue_research,
    handle_record_studio_publish,
    handle_send_brief,
    handle_send_hero,
    handle_studio_asset_status,
    handle_studio_campaign_report,
)
from .registry import ToolRegistry, ToolSpec


def register_rainmaker_tools(registry: ToolRegistry) -> None:
    """Add all Rainmaker command-surface tools. Call once when building the worker session."""

    registry.register(
        ToolSpec(
            name="get_scans",
            description="Latest scan picks and any new tickers today.",
            read_only=True,
            requires_approval=False,
        ),
        _build_get_scans,
    )
    registry.register(
        ToolSpec(
            name="get_pulse",
            description="Current market pulse: regime, lean, confidence.",
            read_only=True,
            requires_approval=False,
        ),
        _build_get_pulse,
    )
    registry.register(
        ToolSpec(
            name="get_trades",
            description="Recent realized (closed) Rainmaker trades.",
            read_only=True,
            requires_approval=False,
        ),
        _build_get_trades,
    )
    registry.register(
        ToolSpec(
            name="get_research",
            description="Latest research digest: completed ideas and summaries.",
            read_only=True,
            requires_approval=False,
        ),
        _build_get_research,
    )
    registry.register(
        ToolSpec(
            name="run_scan",
            description="Start a fresh scan now. Owner only; they must ask to run or refresh.",
            read_only=False,
            requires_approval=True,
        ),
        _build_run_scan,
    )
    registry.register(
        ToolSpec(
            name="queue_research",
            description="Queue research on a topic or ticker. Owner only. Arg: topic.",
            read_only=False,
            requires_approval=True,
        ),
        _build_queue_research,
    )
    registry.register(
        ToolSpec(
            name="get_brief",
            description="Read the owner's morning brief.",
            read_only=True,
            requires_approval=False,
        ),
        _build_get_brief,
    )
    registry.register(
        ToolSpec(
            name="send_brief",
            description="Text the morning brief to the owner. Owner only.",
            read_only=False,
            requires_approval=True,
        ),
        _build_send_brief,
    )
    registry.register(
        ToolSpec(
            name="send_hero",
            description="Text the HERO character card. Owner only.",
            read_only=False,
            requires_approval=True,
        ),
        _build_send_hero,
    )
    registry.register(
        ToolSpec(
            name="list_studio_runs",
            description="List Studio runs and asset counts.",
            read_only=True,
            requires_approval=False,
        ),
        _build_list_studio_runs,
    )
    registry.register(
        ToolSpec(
            name="studio_asset_status",
            description="Status and cost for one Studio asset. Arg: asset_id.",
            read_only=True,
            requires_approval=False,
        ),
        _build_studio_asset_status,
    )
    registry.register(
        ToolSpec(
            name="studio_campaign_report",
            description="Cost and results for a Studio run. Arg: run_id.",
            read_only=True,
            requires_approval=False,
        ),
        _build_studio_campaign_report,
    )
    registry.register(
        ToolSpec(
            name="make_studio_deliverable",
            description="Draft a Studio deliverable and render locally. Owner only. Args: type, run_id.",
            read_only=False,
            requires_approval=False,
        ),
        _build_make_studio,
    )
    registry.register(
        ToolSpec(
            name="record_studio_publish",
            description="Record a Studio publish URL. Owner only. Args: asset_id, url.",
            read_only=False,
            requires_approval=False,
        ),
        _build_record_publish,
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


_OWNER_REFUSAL = "I can only do that for the owner - I didn't recognize your voice."


def _build_list_studio_runs(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def list_studio_runs(context: RunContext) -> str:
        return await handle_list_studio_runs(client)

    return list_studio_runs


def _build_studio_asset_status(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def studio_asset_status(context: RunContext, asset_id: str) -> str:
        return await handle_studio_asset_status(client, asset_id)

    return studio_asset_status


def _build_studio_campaign_report(client: Any, _is_owner: Any, _deps: dict[str, Any]):
    async def studio_campaign_report(context: RunContext, run_id: str) -> str:
        return await handle_studio_campaign_report(client, run_id)

    return studio_campaign_report


def _build_make_studio(client: Any, is_owner: Any, _deps: dict[str, Any]):
    async def make_studio_deliverable(context: RunContext, type: str, run_id: str = "") -> str:
        if is_owner is not None and not is_owner():
            return _OWNER_REFUSAL
        return await handle_make_studio_deliverable(client, type, run_id=run_id)

    return make_studio_deliverable


def _build_record_publish(client: Any, is_owner: Any, _deps: dict[str, Any]):
    async def record_studio_publish(context: RunContext, asset_id: str, url: str) -> str:
        if is_owner is not None and not is_owner():
            return _OWNER_REFUSAL
        return await handle_record_studio_publish(client, asset_id, url)

    return record_studio_publish
