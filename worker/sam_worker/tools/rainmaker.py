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
    async def capture_note(self, body: str, kind: str = "note") -> dict: ...
    async def list_captures(self, limit: int = 8) -> dict: ...
    async def get_brief(self) -> dict: ...
    async def send_brief(self) -> dict: ...
    async def send_hero(self) -> dict: ...
    async def send_email(self, to: str, subject: str, body: str) -> dict: ...
    async def post_sam_alert(self, kind: str, detail: str = "", count: int | None = None) -> dict: ...
    async def request_skill_approval(self, candidate_id: str, summary: str) -> dict: ...
    async def ask_hermes(self, prompt: str) -> dict: ...
    async def list_studio_runs(self, limit: int = 8) -> dict: ...
    async def studio_asset_status(self, asset_id: str) -> dict: ...
    async def studio_campaign_report(self, run_id: str) -> dict: ...
    async def make_studio_deliverable(self, type: str, run_id: str = "") -> dict: ...
    async def record_studio_publish(self, asset_id: str, url: str) -> dict: ...
    async def get_memory_context(self, query: str, token_cap: int = 256) -> dict: ...
    async def get_thread_summary(self) -> dict: ...
    async def write_thread_summary(
        self,
        *,
        summary: str,
        session_id: str = "",
        engagement_id: str = "",
        open_loops: list[str] | None = None,
    ) -> dict: ...
    async def get_engagement(self, engagement_id: str) -> dict: ...
    async def write_memory_turn(
        self,
        *,
        session_id: str,
        surface: str,
        role: str,
        content: str,
        provenance: dict[str, Any] | None = None,
    ) -> dict: ...
    async def get_calendar_events(self, days: int = 7) -> dict: ...
    async def propose_calendar_change(self, **fields: Any) -> dict: ...
    async def commit_calendar_change(
        self, session_id: str, proposal_id: str = ""
    ) -> dict: ...
    async def create_calendar_event(self, **fields: Any) -> dict: ...
    async def update_calendar_event(self, event_id: str, **fields: Any) -> dict: ...
    async def cancel_calendar_event(self, event_id: str) -> dict: ...
    async def text_me(self, body: str, media_url: str = "") -> dict: ...
    async def run_tool(self, name: str, args: dict[str, Any] | None = None) -> dict: ...
    async def get_intake_sync(self, engagement_id: str) -> dict: ...
    async def tick_room(
        self, room_id: str, *, minutes: float = 1.0, tokens: int = 80
    ) -> dict: ...
    async def write_intake(
        self,
        *,
        name: str = "",
        email: str = "",
        source: str = "voice-demo",
        answers: dict[str, Any] | None = None,
    ) -> dict: ...


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

    async def capture_note(self, body: str, kind: str = "note") -> dict:
        return {"ok": True, "shortId": "cap00001", "kind": kind, "body": body}

    async def list_captures(self, limit: int = 8) -> dict:
        return {"ok": True, "captures": [{"kind": "note", "body": "mock note", "status": "open"}]}

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

    async def send_email(self, to: str, subject: str, body: str) -> dict:
        return {"ok": True, "sent": True, "provider": "mock", "to": to, "subject": subject}

    async def post_sam_alert(
        self, kind: str, detail: str = "", count: int | None = None
    ) -> dict:
        return {"ok": True, "sent": True, "kind": kind, "count": count}

    async def request_skill_approval(self, candidate_id: str, summary: str) -> dict:
        return {"ok": True, "code": "MOCK1", "candidateId": candidate_id, "summary": summary}

    async def ask_hermes(self, prompt: str) -> dict:
        return {"ok": True, "text": f"Mock orchestrator idea for: {prompt[:80]}"}

    async def list_studio_runs(self, limit: int = 8) -> dict:
        return {"ok": True, "runs": [{"id": "pov-01", "name": "pov-01", "asset_count": 2}]}

    async def studio_asset_status(self, asset_id: str) -> dict:
        return {"ok": True, "asset": {"id": asset_id, "status": "published", "cost_usd": 0.05}}

    async def studio_campaign_report(self, run_id: str) -> dict:
        return {"ok": True, "run": {"id": run_id, "name": run_id}, "assets": [], "cost_usd": 0}

    async def make_studio_deliverable(self, type: str, run_id: str = "") -> dict:
        return {"ok": True, "asset": {"id": f"{type}-mock", "type": type, "status": "draft"}}

    async def record_studio_publish(self, asset_id: str, url: str) -> dict:
        return {"ok": True, "publish": {"asset_id": asset_id, "url": url, "channel": "web"}}

    async def get_memory_context(self, query: str, token_cap: int = 256) -> dict:
        return {
            "ok": True,
            "items": [
                {
                    "content": f"Mock owner memory relevant to {query}",
                    "role": "user",
                    "provenance": {"surface": "sms"},
                }
            ],
            "tokenCap": token_cap,
        }

    async def get_thread_summary(self) -> dict:
        return {
            "ok": True,
            "thread": {
                "summary": "Mock prior thread about the proposal builder.",
                "openLoops": ["Finish SOW"],
                "updatedAt": 1.0,
            },
        }

    async def write_thread_summary(
        self,
        *,
        summary: str,
        session_id: str = "",
        engagement_id: str = "",
        open_loops: list[str] | None = None,
    ) -> dict:
        return {
            "ok": True,
            "thread": {
                "summary": summary,
                "sessionId": session_id,
                "engagementId": engagement_id,
                "openLoops": open_loops or [],
            },
        }

    async def get_engagement(self, engagement_id: str) -> dict:
        return {
            "ok": True,
            "engagement": {
                "id": engagement_id,
                "client_name": "Mock Client",
                "project_name": "Mock Project",
                "stage": "proposal",
                "answers": {"summary": "Mock builder dump"},
            },
        }

    async def write_memory_turn(
        self,
        *,
        session_id: str,
        surface: str,
        role: str,
        content: str,
        provenance: dict[str, Any] | None = None,
    ) -> dict:
        return {
            "ok": True,
            "turn": {
                "session_id": session_id,
                "surface": surface,
                "role": role,
                "content": content,
                "provenance": provenance or {},
            },
        }

    async def get_calendar_events(self, days: int = 7) -> dict:
        return {
            "ok": True,
            "events": [
                {"id": "mock-event", "summary": "Team sync", "start": "2026-08-19T10:00:00-07:00"}
            ],
        }

    async def propose_calendar_change(self, **fields: Any) -> dict:
        return {
            "ok": True,
            "proposal": {
                "proposal_id": "mock-proposal",
                "readback": f"Create {fields.get('summary') or 'Event'} tomorrow at 10 AM?",
            },
        }

    async def commit_calendar_change(
        self, session_id: str, proposal_id: str = ""
    ) -> dict:
        return {
            "ok": True,
            "result": {
                "proposal_id": proposal_id or "mock-proposal",
                "action": "create",
                "event": {
                    "id": "mock-new",
                    "summary": "Event",
                    "start": "2026-08-20T10:00:00-07:00",
                },
            },
        }

    async def create_calendar_event(self, **fields: Any) -> dict:
        return {
            "ok": True,
            "event": {
                "id": "mock-new",
                "summary": fields.get("summary") or "Event",
                "start": fields.get("start"),
            },
        }

    async def update_calendar_event(self, event_id: str, **fields: Any) -> dict:
        return {
            "ok": True,
            "event": {"id": event_id, "summary": fields.get("summary") or "Updated", "start": fields.get("start")},
        }

    async def cancel_calendar_event(self, event_id: str) -> dict:
        return {"ok": True, "event": {"id": event_id, "deleted": True}}

    async def text_me(self, body: str, media_url: str = "") -> dict:
        return {"ok": True, "sent": True, "reason": None}

    async def run_tool(self, name: str, args: dict[str, Any] | None = None) -> dict:
        return {"ok": True, "name": name, "text": f"mock {name}"}

    async def get_intake_sync(self, engagement_id: str) -> dict:
        return {
            "ok": True,
            "engagementId": engagement_id,
            "complete": False,
            "gaps": [{"field": "discovery", "questionId": "pages", "question": "How many pages?"}],
            "focus": {"field": None, "questionId": "pages"},
            "answers": [],
            "form_data": {"projectSummary": "Mock job"},
        }

    async def tick_room(
        self, room_id: str, *, minutes: float = 1.0, tokens: int = 80
    ) -> dict:
        return {"ok": True, "room": {"id": room_id}, "minutes": minutes, "tokens": tokens}

    async def write_intake(
        self,
        *,
        name: str = "",
        email: str = "",
        source: str = "voice-demo",
        answers: dict[str, Any] | None = None,
    ) -> dict:
        return {
            "ok": True,
            "engagement": {"id": "eng-mock", "stage": "proposal", "source": source},
            "name": name,
            "email": email,
            "answers": answers or {},
        }


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
    CAPTURE_PATH = "/capture"
    CAPTURE_TODAY_PATH = "/capture/today"
    BRIEF_PREVIEW_PATH = "/notify/owner-brief/preview"
    BRIEF_SEND_PATH = "/notify/owner-brief"
    HERO_SEND_PATH = "/notify/test-hero"
    OWNER_EMAIL_PATH = "/notify/owner-email"
    SAM_ALERT_PATH = "/ops/sam-alert"
    SKILL_APPROVAL_PATH = "/samuel/skill-approval"
    ASK_HERMES_PATH = "/samuel/ask-hermes"
    DELIVER_PATH = "/notify/deliver"
    TOOL_PATH = "/samuel/tool"
    STUDIO_RUNS_PATH = "/studio/runs"
    STUDIO_ASSET_PATH = "/studio/asset"
    STUDIO_REPORT_PATH = "/studio/campaign/report"
    STUDIO_MAKE_PATH = "/studio/make"
    STUDIO_PUBLISH_PATH = "/studio/publish"
    MEMORY_CONTEXT_PATH = "/samuel/memory/context"
    MEMORY_TURNS_PATH = "/samuel/memory/turns"
    MEMORY_THREAD_PATH = "/samuel/memory/thread"
    CALENDAR_EVENTS_PATH = "/calendar/events"
    CALENDAR_PROPOSALS_PATH = "/calendar/proposals"
    INTAKE_PATH = "/intake"
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

    async def _patch(
        self, path: str, body: dict[str, Any] | None = None, *, timeout: float | None = None
    ) -> dict:
        import httpx

        url = self.base_url + path
        tmo = self.timeout if timeout is None else timeout
        try:
            if self._client is not None:
                resp = await self._client.patch(
                    url, json=body or {}, headers=self._headers(), timeout=tmo
                )
            else:
                async with httpx.AsyncClient(timeout=tmo) as client:
                    resp = await client.patch(url, json=body or {}, headers=self._headers())
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

    async def _delete(self, path: str, *, timeout: float | None = None) -> dict:
        import httpx

        url = self.base_url + path
        tmo = self.timeout if timeout is None else timeout
        try:
            if self._client is not None:
                resp = await self._client.delete(url, headers=self._headers(), timeout=tmo)
            else:
                async with httpx.AsyncClient(timeout=tmo) as client:
                    resp = await client.delete(url, headers=self._headers())
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

    async def capture_note(self, body: str, kind: str = "note") -> dict:
        res = await self._post(
            self.CAPTURE_PATH,
            body={"body": body, "kind": kind or "note", "surface": "voice"},
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        item = data.get("capture") or {}
        return {
            "ok": True,
            "shortId": data.get("short_id") or item.get("short_id") or "",
            "kind": item.get("kind") or kind,
            "body": item.get("body") or body,
        }

    async def list_captures(self, limit: int = 8) -> dict:
        res = await self._get(self.CAPTURE_TODAY_PATH, params={"limit": limit})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, "captures": data.get("captures") or []}

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

    async def send_email(self, to: str, subject: str, body: str) -> dict:
        res = await self._post(
            self.OWNER_EMAIL_PATH,
            body={"to": to, "subject": subject, "body": body},
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, **data}

    async def post_sam_alert(
        self, kind: str, detail: str = "", count: int | None = None
    ) -> dict:
        body: dict[str, Any] = {"kind": kind, "detail": detail}
        if count is not None:
            body["count"] = count
        res = await self._post(self.SAM_ALERT_PATH, body=body)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        return {"ok": True, **(res.get("data") or {})}

    async def request_skill_approval(self, candidate_id: str, summary: str) -> dict:
        res = await self._post(
            self.SKILL_APPROVAL_PATH,
            body={"candidateId": candidate_id, "summary": summary},
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        return {"ok": True, **(res.get("data") or {})}

    async def ask_hermes(self, prompt: str) -> dict:
        res = await self._post(self.ASK_HERMES_PATH, body={"prompt": prompt})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, "text": data.get("text") or "", "reason": data.get("reason")}

    async def list_studio_runs(self, limit: int = 8) -> dict:
        res = await self._get(self.STUDIO_RUNS_PATH, params={"limit": limit})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, "runs": data.get("runs") or []}

    async def studio_asset_status(self, asset_id: str) -> dict:
        res = await self._get(f"{self.STUDIO_ASSET_PATH}/{asset_id}")
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, "asset": data.get("asset") or data}

    async def studio_campaign_report(self, run_id: str) -> dict:
        res = await self._get(self.STUDIO_REPORT_PATH, params={"run_id": run_id})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        return {"ok": True, **(res.get("data") or {})}

    async def make_studio_deliverable(self, type: str, run_id: str = "") -> dict:
        body: dict[str, Any] = {"type": type}
        if run_id:
            body["run_id"] = run_id
        res = await self._post(self.STUDIO_MAKE_PATH, body=body)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        return {"ok": True, **(res.get("data") or {})}

    async def record_studio_publish(self, asset_id: str, url: str) -> dict:
        res = await self._post(self.STUDIO_PUBLISH_PATH, body={"asset_id": asset_id, "url": url})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, "publish": data.get("publish") or data}

    async def get_memory_context(self, query: str, token_cap: int = 256) -> dict:
        res = await self._get(
            self.MEMORY_CONTEXT_PATH,
            params={
                "query": (query or "")[:2000],
                "tokenCap": max(16, min(int(token_cap or 256), 2048)),
            },
            timeout=min(self.timeout, 0.6),
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {
            "ok": True,
            "items": data.get("items") or [],
            "personId": data.get("personId"),
            "tokenCap": data.get("tokenCap"),
        }

    async def get_thread_summary(self) -> dict:
        res = await self._get(
            self.MEMORY_THREAD_PATH,
            timeout=min(self.timeout, 0.6),
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        return {"ok": True, **(res.get("data") or {})}

    async def write_thread_summary(
        self,
        *,
        summary: str,
        session_id: str = "",
        engagement_id: str = "",
        open_loops: list[str] | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "summary": (summary or "")[:4000],
            "sessionId": (session_id or "")[:256],
            "engagementId": (engagement_id or "")[:128],
        }
        if open_loops:
            body["openLoops"] = [str(item)[:320] for item in open_loops[:12]]
        res = await self._post(
            self.MEMORY_THREAD_PATH,
            body=body,
            timeout=min(self.timeout, 0.8),
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, "thread": data.get("thread") or {}}

    async def get_engagement(self, engagement_id: str) -> dict:
        engagement_id = (engagement_id or "").strip()
        if not engagement_id:
            return {"ok": False, "error": "missing_engagement_id"}
        res = await self._get(
            f"{self.INTAKE_PATH}/{engagement_id}",
            timeout=min(self.timeout, 0.8),
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        return {"ok": True, **(res.get("data") or {})}

    async def write_memory_turn(
        self,
        *,
        session_id: str,
        surface: str,
        role: str,
        content: str,
        provenance: dict[str, Any] | None = None,
    ) -> dict:
        res = await self._post(
            self.MEMORY_TURNS_PATH,
            body={
                "sessionId": (session_id or "sam-worker")[:256],
                "surface": (surface or "voice")[:32],
                "role": (role or "")[:32],
                "content": (content or "")[:8000],
                "provenance": provenance or {},
            },
            timeout=min(self.timeout, 0.6),
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, "turn": data.get("turn") or {}}

    async def get_calendar_events(self, days: int = 7) -> dict:
        res = await self._get(self.CALENDAR_EVENTS_PATH, params={"days": days})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": bool(data.get("ok", True)), "events": data.get("events") or [], "error": data.get("error")}

    async def propose_calendar_change(self, **fields: Any) -> dict:
        res = await self._post(self.CALENDAR_PROPOSALS_PATH, body=fields)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error") or "calendar_proposal_failed"}
        return {"ok": True, "proposal": data.get("proposal") or {}}

    async def commit_calendar_change(
        self, session_id: str, proposal_id: str = ""
    ) -> dict:
        res = await self._post(
            f"{self.CALENDAR_PROPOSALS_PATH}/commit",
            body={"session_id": session_id, "proposal_id": proposal_id},
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error") or "calendar_commit_failed"}
        return {"ok": True, "result": data.get("result") or {}}

    async def create_calendar_event(self, **fields: Any) -> dict:
        res = await self._post(self.CALENDAR_EVENTS_PATH, body=fields)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error") or "calendar_create_failed"}
        return {"ok": True, "event": data.get("event") or {}}

    async def update_calendar_event(self, event_id: str, **fields: Any) -> dict:
        res = await self._patch(f"{self.CALENDAR_EVENTS_PATH}/{event_id}", body=fields)
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error") or "calendar_update_failed"}
        return {"ok": True, "event": data.get("event") or {}}

    async def cancel_calendar_event(self, event_id: str) -> dict:
        res = await self._delete(f"{self.CALENDAR_EVENTS_PATH}/{event_id}")
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        if not data.get("ok"):
            return {"ok": False, "error": data.get("error") or "calendar_delete_failed"}
        return {"ok": True, "event": data.get("event") or {}}

    async def text_me(self, body: str, media_url: str = "") -> dict:
        payload: dict[str, Any] = {"body": body}
        if media_url:
            payload["mediaUrl"] = media_url
        res = await self._post(self.DELIVER_PATH, body=payload)
        if not res["ok"]:
            return {"ok": False, "sent": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": bool(data.get("ok") or data.get("sent")), **data}

    async def run_tool(self, name: str, args: dict[str, Any] | None = None) -> dict:
        res = await self._post(self.TOOL_PATH, body={"name": name, "args": args or {}})
        if not res["ok"]:
            return {"ok": False, "error": res["error"], "text": ""}
        data = res.get("data") or {}
        return {"ok": True, **data}

    async def get_intake_sync(self, engagement_id: str) -> dict:
        res = await self._get(f"{self.INTAKE_PATH}/{engagement_id}/sync")
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": True, **data}

    async def tick_room(
        self, room_id: str, *, minutes: float = 1.0, tokens: int = 80
    ) -> dict:
        path = f"/moderate/rooms/{room_id}/tick"
        res = await self._post(path, body={"minutes": minutes, "tokens": tokens})
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": bool(data.get("ok", True)), **data}

    async def write_intake(
        self,
        *,
        name: str = "",
        email: str = "",
        source: str = "voice-demo",
        answers: dict[str, Any] | None = None,
    ) -> dict:
        res = await self._post(
            self.INTAKE_PATH,
            body={
                "name": name,
                "email": email,
                "source": source,
                "answers": answers or {},
            },
        )
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        data = res.get("data") or {}
        return {"ok": bool(data.get("ok", True)), **data}
