"""Rainmaker command surface (ADR-10): the function-call tools Samuel uses to operate
Rainmaker over existing rm_api routes. READ-ONLY first; every state-changing action is gated
behind explicit user approval. Autonomous live trading is a later branch (out of scope).

Phase 4 ships the tool *schema* + a mock client so the LLM tool layer can be developed without
hitting prod. Phase 5 (SAM-005) implements HttpRainmakerClient (httpx -> rm_api).

Route map (verified against rm_api):
  get_scans  -> GET /scan/latest          (public; latest scheduled scan symbols + new tickers)
  get_pulse  -> GET /pulse/bias?futures=0 (public; Morning Bias - lighter than /pulse/snapshot)
  get_trades -> GET /trade/round-trips    (auth: X-RM-CRON-TOKEN; realized FIFO round-trips)

Why /pulse/bias over /pulse/snapshot: the bias endpoint returns a compact MorningBias
(market label + pct + confidence) that is the speakable summary Samuel needs, without the
full per-symbol quote payload. Why /trade/round-trips for get_trades: it is the read-only
realized (closed) trade view; live OPEN positions require a Schwab positions sync that is not
a read-only route today, so status="open" returns the realized view with an explicit note.
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
    # Tier-T triggers + research read (owner-gated at the tool layer, not here).
    async def run_scan(self) -> dict: ...
    async def queue_research(self, prompt: str) -> dict: ...
    async def get_research(self, limit: int = 3) -> dict: ...
    async def get_brief(self) -> dict: ...
    async def send_brief(self) -> dict: ...
    async def send_hero(self) -> dict: ...


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

    async def run_scan(self) -> dict:
        return {"ok": True, "newSymbols": ["MOCK"], "count": 1}

    async def queue_research(self, prompt: str) -> dict:
        return {"ok": True, "shortId": "mock1234", "status": "queued", "queuedAhead": 0}

    async def get_research(self, limit: int = 3) -> dict:
        return {"ok": True, "items": [{"prompt": "mock idea", "summary": "mock summary"}]}

    async def get_brief(self) -> dict:
        return {
            "ok": True,
            "message": "Good morning - mock brief. Top priority: review scans.",
            "weekend": False,
        }

    async def send_brief(self) -> dict:
        return {"ok": True, "sent": True, "message": "Mock brief sent to your phone."}

    async def send_hero(self) -> dict:
        return {"ok": True, "sent": True, "reason": "mock_mms"}


class HttpRainmakerClient:
    """Read-only rm_api client (SAM-005). httpx + ``X-RM-CRON-TOKEN``.

    Every method returns a structured dict with ``ok``; failures degrade to
    ``{"ok": False, "error": ...}`` so the tool layer never raises into the
    voice loop (the canon prompt tells Samuel to say he couldn't pull data
    rather than invent it).
    """

    SCANS_PATH = "/scan/latest"
    PULSE_PATH = "/pulse/bias"
    TRADES_PATH = "/trade/round-trips"
    SCAN_RUN_PATH = "/scan/scheduled"
    RESEARCH_IDEAS_PATH = "/research/ideas"
    RESEARCH_DIGEST_PATH = "/research/digest"
    BRIEF_PREVIEW_PATH = "/notify/owner-brief/preview"
    BRIEF_SEND_PATH = "/notify/owner-brief"
    HERO_SEND_PATH = "/notify/test-hero"
    _LONG_TIMEOUT = 30.0

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 15.0,
        client: Any = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = timeout
        # Optional injected httpx.AsyncClient (tests pass a MockTransport-backed one).
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["X-RM-CRON-TOKEN"] = self.token
        return headers

    async def _get(self, path: str, params: dict[str, Any] | None = None, *, timeout: float | None = None) -> dict:
        import httpx

        url = self.base_url + path
        tmo = self.timeout if timeout is None else timeout
        try:
            if self._client is not None:
                resp = await self._client.get(
                    url, params=params, headers=self._headers(), timeout=tmo
                )
            else:
                async with httpx.AsyncClient(timeout=tmo) as client:
                    resp = await client.get(url, params=params, headers=self._headers())
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout"}
        except httpx.HTTPError as exc:  # connect/transport errors
            return {"ok": False, "error": f"request_error: {exc}"[:200]}
        if resp.status_code != 200:
            return {"ok": False, "error": f"http_{resp.status_code}"}
        try:
            return {"ok": True, "data": resp.json()}
        except ValueError:
            return {"ok": False, "error": "bad_json"}

    async def _post(
        self, path: str, body: dict[str, Any] | None = None, *, timeout: float | None = None
    ) -> dict:
        import httpx

        url = self.base_url + path
        tmo = self.timeout if timeout is None else timeout
        try:
            if self._client is not None:
                resp = await self._client.post(
                    url, json=body or {}, headers=self._headers(), timeout=tmo
                )
            else:
                async with httpx.AsyncClient(timeout=tmo) as client:
                    resp = await client.post(url, json=body or {}, headers=self._headers())
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout"}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"request_error: {exc}"[:200]}
        if resp.status_code != 200:
            return {"ok": False, "error": f"http_{resp.status_code}"}
        try:
            return {"ok": True, "data": resp.json()}
        except ValueError:
            return {"ok": False, "error": "bad_json"}

    async def get_scans(self, limit: int = 10) -> dict:
        res = await self._get(self.SCANS_PATH)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        all_symbols = [s for s in (data.get("symbols") or []) if s]
        capped = max(0, int(limit)) if limit is not None else len(all_symbols)
        return {
            "ok": True,
            "symbols": all_symbols[:capped],
            "newSymbols": [s for s in (data.get("newSymbols") or []) if s],
            "count": len(all_symbols),
            "at": data.get("at"),
        }

    async def get_pulse(self) -> dict:
        # futures=0: market-track bias only; lighter and avoids futures quote fetch.
        res = await self._get(self.PULSE_PATH, params={"futures": 0})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data")
        if not data:
            return {
                "ok": True,
                "available": False,
                "note": "No morning bias available yet (market may be closed).",
            }
        market = (data.get("market") or {})
        return {
            "ok": True,
            "available": True,
            "label": market.get("label"),
            "pct": market.get("pct"),
            "confidence": market.get("confidence"),
            "narrowTape": bool(data.get("narrowTape", False)),
            "conflict": bool(data.get("conflict", False)),
        }

    async def get_trades(self, status: str | None = None) -> dict:
        res = await self._get(self.TRADES_PATH)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        round_trips = data.get("roundTrips") or []
        out = {
            "ok": True,
            "status": status or "closed",
            "trades": round_trips,
            "count": len(round_trips),
        }
        if status == "open":
            out["note"] = (
                "Showing realized round-trips. Live open positions are not exposed "
                "read-only yet (requires a Schwab positions sync)."
            )
        return out

    async def run_scan(self) -> dict:
        """Trigger the scheduled H-001 scan (Tier-T). Posts an empty body; rm_api caches
        the result and surfaces new tickers. ~60s server-side."""
        res = await self._post(self.SCAN_RUN_PATH, body={})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {
            "ok": True,
            "newSymbols": [s for s in (data.get("newSymbols") or []) if s],
            "count": int(data.get("count") or 0),
        }

    async def queue_research(self, prompt: str) -> dict:
        """Queue a research idea (Tier-T). Mirrors the SMS RESEARCH command."""
        body = {"prompt": prompt, "tags": ["voice"], "source_hint": "voice"}
        res = await self._post(self.RESEARCH_IDEAS_PATH, body=body)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {
            "ok": True,
            "shortId": data.get("short_id") or (str(data.get("id") or "")[:8]),
            "status": data.get("status") or "queued",
            "queuedAhead": int(data.get("queued_ahead") or 0),
        }

    async def get_research(self, limit: int = 3) -> dict:
        """Read the recent research digest (done ideas + summaries)."""
        res = await self._get(self.RESEARCH_DIGEST_PATH, params={"limit": limit})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        items = data.get("research_digest") or []
        return {"ok": True, "items": items[:limit], "count": len(items)}

    async def get_brief(self) -> dict:
        """Assemble the owner morning brief (read-only preview). Can take ~20s."""
        res = await self._get(self.BRIEF_PREVIEW_PATH, timeout=self._LONG_TIMEOUT)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        message = (data.get("message") or "").strip()
        if not message:
            return {"ok": False, "error": "empty_brief"}
        return {
            "ok": True,
            "message": message,
            "weekend": bool(data.get("weekend")),
        }

    async def send_brief(self) -> dict:
        """SMS the assembled morning brief to the owner (Tier-T). Mirrors SMS BRIEF."""
        res = await self._post(self.BRIEF_SEND_PATH, body={"send": True}, timeout=self._LONG_TIMEOUT)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {
            "ok": True,
            "sent": bool(data.get("sent")),
            "reason": data.get("reason"),
            "message": (data.get("message") or "")[:200],
        }

    async def send_hero(self) -> dict:
        """MMS the Samuel HERO character card to the owner phone. Mirrors SMS HERO."""
        res = await self._post(self.HERO_SEND_PATH, body={}, timeout=self._LONG_TIMEOUT)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {
            "ok": True,
            "sent": bool(data.get("sent")),
            "reason": data.get("reason"),
            "ascii": bool(data.get("ascii")),
        }
