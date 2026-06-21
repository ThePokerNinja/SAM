"""Rainmaker command surface (ADR-10): the function-call tools Samuel uses to operate
Rainmaker over existing rm_api routes. READ-ONLY first; every state-changing action is gated
behind explicit user approval. Autonomous live trading is a later branch (out of scope).

Phase 4 ships the tool *schema* + a mock client so the LLM tool layer can be developed without
hitting prod. Phase 5 swaps MockRainmakerClient for HttpRainmakerClient (httpx -> rm_api).
"""

from __future__ import annotations

from typing import Any, Protocol

# Tool schema advertised to the brain. Read-only tools run freely; write tools must set
# requires_approval=True and are confirmed with the user before execution.
TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "get_scans",
        "description": "List the latest Rainmaker scans (symbols, posture, signals).",
        "read_only": True,
        "params": {"limit": "int (optional, default 10)"},
    },
    {
        "name": "get_pulse",
        "description": "Current market pulse / regime summary.",
        "read_only": True,
        "params": {},
    },
    {
        "name": "get_trades",
        "description": "Recent closed/open trades (view only).",
        "read_only": True,
        "params": {"status": "open|closed (optional)"},
    },
    {
        "name": "draft_order",
        "description": "Draft (do NOT place) an order for user review.",
        "read_only": False,
        "requires_approval": True,
        "params": {"symbol": "str", "side": "buy|sell", "qty": "number"},
    },
    {
        "name": "send_brief",
        "description": "Send the owner brief via rm_api (state-changing).",
        "read_only": False,
        "requires_approval": True,
        "params": {},
    },
]


class RainmakerClient(Protocol):
    async def get_scans(self, limit: int = 10) -> dict: ...
    async def get_pulse(self) -> dict: ...
    async def get_trades(self, status: str | None = None) -> dict: ...


class MockRainmakerClient:
    """Returns canned shapes matching rm_api so the tool/brain layer is testable offline."""

    async def get_scans(self, limit: int = 10) -> dict:
        return {
            "ok": True,
            "scans": [
                {"symbol": "NVDA", "posture": "constructive", "signal": "momentum"},
                {"symbol": "AAPL", "posture": "neutral", "signal": "coil"},
            ][:limit],
        }

    async def get_pulse(self) -> dict:
        return {"ok": True, "regime": "risk-on", "breadth": 0.62, "note": "mock pulse"}

    async def get_trades(self, status: str | None = None) -> dict:
        return {"ok": True, "status": status or "all", "trades": []}


class HttpRainmakerClient:
    """Real client — STUB for Phase 5. Wrap rm_api routes with httpx + RM_API_TOKEN."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token

    async def get_scans(self, limit: int = 10) -> dict:
        raise NotImplementedError("HttpRainmakerClient is a Phase 5 stub.")

    async def get_pulse(self) -> dict:
        raise NotImplementedError("HttpRainmakerClient is a Phase 5 stub.")

    async def get_trades(self, status: str | None = None) -> dict:
        raise NotImplementedError("HttpRainmakerClient is a Phase 5 stub.")
