"""SAM-006: grounding logic behind Samuel's read-only Rainmaker tools.

Kept stdlib-only (no LiveKit import) so the formatting/grounding is unit-testable offline:

  - ``handle_*`` async functions: take a ``RainmakerClient`` and return a short, spoken
    string. They never raise - on a tool failure they return an honest "couldn't pull it"
    line so Samuel degrades to the canon behavior instead of inventing data.
  - ``build_rainmaker_client(settings)``: picks the mock vs http client (SAM_MOCK_RM /
    missing config -> mock).

The LiveKit ``function_tool`` wrappers are built from ``registry.py`` + ``rainmaker_registry.py``
(SAM-035) so new tools register without editing ``agent.py``.
"""

from __future__ import annotations

from typing import Any

from .rainmaker import HttpRainmakerClient, MockRainmakerClient, RainmakerClient

_MAX_SPOKEN = 280  # keep tool output short; the canon prompt wants 1-2 spoken sentences


def build_rainmaker_client(settings: Any) -> RainmakerClient:
    """Choose the live rm_api client, or the mock when configured/unconfigured."""
    if getattr(settings, "sam_mock_rm", False):
        return MockRainmakerClient()
    base = getattr(settings, "rm_api_base_url", "") or ""
    if not base:
        return MockRainmakerClient()
    return HttpRainmakerClient(base, getattr(settings, "rm_api_token", "") or "")


def _fail(kind: str) -> str:
    return f"I couldn't pull the {kind} right now. I won't guess - try again in a moment."


async def handle_get_scans(client: RainmakerClient, limit: int = 5) -> str:
    res = await client.get_scans(limit=limit)
    if not res.get("ok"):
        return _fail("latest scans")
    symbols = res.get("symbols") or [
        s.get("symbol") if isinstance(s, dict) else s for s in (res.get("scans") or [])
    ]
    symbols = [s for s in symbols if s]
    if not symbols:
        return "There are no fresh scan picks on the board right now."
    new = res.get("newSymbols") or []
    line = "Latest scan picks: " + ", ".join(symbols[:limit]) + "."
    if new:
        line += " New today: " + ", ".join(new[:limit]) + "."
    return line[:_MAX_SPOKEN]


async def handle_get_pulse(client: RainmakerClient) -> str:
    res = await client.get_pulse()
    if not res.get("ok"):
        return _fail("market pulse")
    if res.get("available") is False:
        return "There's no morning bias posted yet - the market may be closed."
    # Mock client returns regime/breadth; http client returns label/pct/confidence.
    label = res.get("label") or res.get("regime")
    pct = res.get("pct")
    conf = res.get("confidence")
    if not label:
        return "The market pulse is unclear right now."
    line = f"Market pulse: {label}"
    if isinstance(pct, (int, float)):
        line += f", {int(pct)} out of 100"
    if conf:
        line += f", {conf} confidence"
    line += "."
    if res.get("narrowTape"):
        line += " Tape is narrow."
    return line[:_MAX_SPOKEN]


def _fmt_trade(rt: dict) -> str | None:
    sym = rt.get("symbol")
    if not sym:
        return None
    try:
        pnl = (float(rt.get("exit")) - float(rt.get("entry"))) * float(rt.get("qty", 0))
        sign = "+" if pnl >= 0 else "-"
        return f"{sym} {sign}${abs(pnl):.0f}"
    except (TypeError, ValueError):
        return str(sym)


async def handle_get_trades(client: RainmakerClient, status: str | None = None) -> str:
    res = await client.get_trades(status=status)
    if not res.get("ok"):
        return _fail("trade history")
    trades = res.get("trades") or []
    if not trades:
        return "There are no recorded trades to report."
    parts = [p for p in (_fmt_trade(t) for t in trades[:3]) if p]
    line = f"Recent {res.get('status', 'closed')} trades: " + "; ".join(parts) + "."
    if res.get("note"):
        line += " " + res["note"]
    return line[:_MAX_SPOKEN]


async def handle_run_scan(client: RainmakerClient) -> str:
    """Tier-T: kick off a scan. The caller fires this without awaiting the full ~60s run
    (see agent.py background-fire), so this returns a short ack, not results."""
    res = await client.run_scan()
    if not res.get("ok"):
        return _fail("scan run")
    new = res.get("newSymbols") or []
    if new:
        return "Scan finished. New tickers: " + ", ".join(new[:6]) + "."
    count = res.get("count") or 0
    return f"Scan finished - {count} on the board, nothing brand new."


async def handle_queue_research(client: RainmakerClient, prompt: str) -> str:
    prompt = (prompt or "").strip()
    if len(prompt) < 4:
        return "Give me a bit more to research and I'll queue it."
    res = await client.queue_research(prompt)
    if not res.get("ok"):
        return _fail("research request")
    ahead = res.get("queuedAhead") or 0
    sid = res.get("shortId") or ""
    where = "next up" if not ahead else f"{ahead} ahead of it"
    return f"Queued your research, {where}. Ask me for the research digest later to read it."


async def handle_get_research(client: RainmakerClient, limit: int = 3) -> str:
    res = await client.get_research(limit=limit)
    if not res.get("ok"):
        return _fail("research digest")
    items = res.get("items") or []
    if not items:
        return "The research digest is empty right now."
    bits = []
    for it in items[:3]:
        summary = (it.get("summary") or it.get("prompt") or "").strip()
        if summary:
            bits.append(summary[:90])
    if not bits:
        return "I have research on file but no summaries to read yet."
    return ("Recent research: " + " | ".join(bits) + ".")[:_MAX_SPOKEN]


_BRIEF_SPOKEN_MAX = 520  # brief is longer than other tools; still cap for one voice turn


async def handle_get_brief(client: RainmakerClient) -> str:
    res = await client.get_brief()
    if not res.get("ok"):
        return _fail("morning brief")
    message = (res.get("message") or "").strip()
    if not message:
        return "I couldn't assemble a brief right now."
    # Speak the opening lines; offer SMS for the full text if truncated.
    spoken = message.replace("\n", ". ").strip()
    if len(spoken) > _BRIEF_SPOKEN_MAX:
        spoken = spoken[: _BRIEF_SPOKEN_MAX - 40].rsplit(".", 1)[0] + ". "
        spoken += "Say text me the brief if you want the full version on your phone."
    return spoken


async def handle_send_brief(client: RainmakerClient) -> str:
    res = await client.send_brief()
    if not res.get("ok"):
        return _fail("brief text")
    if res.get("sent"):
        return "Done - I texted you the morning brief."
    reason = res.get("reason") or "send_failed"
    return f"I couldn't text the brief right now ({reason})."


async def handle_list_studio_runs(client: RainmakerClient) -> str:
    res = await client.list_studio_runs()
    if not res.get("ok"):
        return _fail("studio runs")
    runs = res.get("runs") or []
    if not runs:
        return "There are no studio runs yet."
    parts = [str(r.get("name") or r.get("id")) for r in runs[:5]]
    return ("Studio runs: " + ", ".join(parts) + ".")[:_MAX_SPOKEN]


async def handle_studio_asset_status(client: RainmakerClient, asset_id: str) -> str:
    res = await client.studio_asset_status(asset_id)
    if not res.get("ok"):
        return _fail("asset status")
    a = res.get("asset") or {}
    return f"Asset {a.get('id')}: {a.get('status')}, ${float(a.get('cost_usd') or 0):.2f}."[:_MAX_SPOKEN]


async def handle_studio_campaign_report(client: RainmakerClient, run_id: str) -> str:
    res = await client.studio_campaign_report(run_id)
    if not res.get("ok"):
        return _fail("campaign report")
    run = res.get("run") or {}
    n = len(res.get("assets") or [])
    return f"Report {run.get('name') or run_id}: {n} assets, ${float(res.get('cost_usd') or 0):.2f}."[:_MAX_SPOKEN]


async def handle_make_studio_deliverable(client: RainmakerClient, type: str, run_id: str = "") -> str:
    res = await client.make_studio_deliverable(type, run_id=run_id)
    if res.get("needs_approval"):
        return f"Make paused: {res.get('reason') or 'that step would spend money'}."[:_MAX_SPOKEN]
    if not res.get("ok"):
        return _fail("studio make")
    a = res.get("asset") or {}
    return f"Drafted {a.get('type') or type} as {a.get('id')}. Open Studio to review."[:_MAX_SPOKEN]


async def handle_record_studio_publish(client: RainmakerClient, asset_id: str, url: str) -> str:
    res = await client.record_studio_publish(asset_id, url)
    if not res.get("ok"):
        return _fail("publish record")
    return f"Recorded publish for {asset_id}."[:_MAX_SPOKEN]


async def handle_send_hero(client: RainmakerClient) -> str:
    res = await client.send_hero()
    if not res.get("ok"):
        return _fail("hero card")
    if res.get("sent"):
        return "Your HERO card is on its way - check your texts for the image."
    if res.get("ascii"):
        return "Twilio couldn't send the image, so I texted you an ASCII version of the card."
    reason = res.get("reason") or "send_failed"
    return f"I couldn't send the HERO card right now ({reason})."
