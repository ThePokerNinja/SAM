"""Live-trading plan Wave 2: confirm-first trading discussion pack + save handler."""

from __future__ import annotations

import asyncio

from sam_worker.packs.registry import PackRegistry
from sam_worker.session import TRADING_OFFER_LINE, build_session, pack_for_kind, route_session_kind
from sam_worker.tools.handlers import handle_save_trading_discussion
from sam_worker.tools.rainmaker import MockRainmakerClient
from sam_worker.tools.select import TRADING_DISCUSSION_TOOLS, keeps_whole_pack, select_tools_for_utterance


def test_trade_talk_asks_first_and_yes_starts_the_pack() -> None:
    session = build_session(session_id="portal-owner", surface="portal")
    # Adjacent talk does not switch; it only earns the question.
    assert session.activate_from_utterance("let's run the numbers on NVDA") is False
    assert session.kind == "trading" and session.trading_offer is True
    assert session.activate_from_utterance("yeah, let's do it") is True
    assert session.kind == "trading_discussion" and session.pack == "trading_discussion"
    assert session.activate_from_utterance("back to trading") is True
    assert session.kind == "trading"


def test_phone_offer_is_spoken_verbatim_to_the_owner_only() -> None:
    # The 2026-10-17 call: the flag was set but gpt-4o-mini never asked the question.
    session = build_session(session_id="call-_+18318186191_x", surface="phone")
    session.room_name = "call-_+18318186191_x"
    session.activate_from_utterance("Let's talk trades.")
    assert session.trading_offer_reply(is_owner=True) == TRADING_OFFER_LINE == "Start a trading discussion?"
    assert session.activate_from_utterance("Yes.") is True
    assert session.kind == "trading_discussion"
    assert session.trading_offer_reply(is_owner=True) is None
    guest = build_session(session_id="call-_+15550001111_y", surface="phone")
    guest.activate_from_utterance("Let's talk trades.")
    assert guest.trading_offer_reply(is_owner=False) is None
    assert guest.activate_from_utterance("yes") is False


def test_no_after_the_offer_stays_put_and_clears_it() -> None:
    session = build_session(session_id="portal-owner", surface="portal")
    session.activate_from_utterance("what if we sized up tomorrow")
    assert session.activate_from_utterance("no, just the pulse") is False
    assert session.kind == "trading" and session.trading_offer is False
    # A later bare "yes" is not a stale confirm.
    assert session.activate_from_utterance("yes") is False


def test_explicit_start_routes_on_portal_and_phone() -> None:
    assert route_session_kind(surface="portal", keyword="start a trading discussion") == "trading_discussion"
    assert route_session_kind(surface="phone", keyword="trading discussion", room_name="call-_+1555_abc") == "trading_discussion"
    assert route_session_kind(surface="portal", keyword="trading discussion", room_name="builder-e1") == "intake"
    assert route_session_kind(surface="portal", keyword="what are today's picks") == "trading"
    assert pack_for_kind("trading_discussion") == "trading_discussion"


def test_pack_scopes_tools_and_forbids_orders() -> None:
    reg = PackRegistry()
    pack = reg.get("trading_discussion")
    assert pack.tools == TRADING_DISCUSSION_TOOLS
    assert "no_orders_by_voice" in pack.safety_rules
    assert "YES code by text" in pack.persona_overlay
    assert reg.tools_for("trading_discussion", ["get_pulse", "capture_note", "run_backtest"]) == ["get_pulse", "run_backtest"]


def test_select_loads_trading_tools_on_trade_words() -> None:
    names = select_tools_for_utterance("backtest AVGO for me")
    assert {"run_backtest", "save_trading_discussion", "get_account", "get_trading_status"} <= set(names)
    assert "get_account" in select_tools_for_utterance("what's the equity in my account")
    assert select_tools_for_utterance("how much does Rainmaker cost") == []  # pricing guard wins
    assert "run_backtest" not in select_tools_for_utterance("what is the pulse?")


def test_router_keeps_every_pack_tool_on_a_bare_yes() -> None:
    # The per-utterance subset for "yes" has no trading tool, so the pack must bypass it.
    assert not ({"run_backtest"} & set(select_tools_for_utterance("yes")))
    assert keeps_whole_pack(set(TRADING_DISCUSSION_TOOLS))
    assert keeps_whole_pack({"run_backtest", "get_account"})
    assert keeps_whole_pack({"get_calendar_events", "propose_calendar_change"})
    assert not keeps_whole_pack({"run_backtest", "capture_note"})
    assert not keeps_whole_pack(set())


def test_save_handler_posts_one_structured_call() -> None:
    class Spy(MockRainmakerClient):
        calls: list[tuple[str, dict]] = []

        async def run_tool(self, name, args=None):
            self.calls.append((name, dict(args or {})))
            return {"ok": True, "name": name, "text": "Saved trading discussion #ab12cd. Tonight's night shift reads it."}

    spy = Spy()
    out = asyncio.run(
        handle_save_trading_discussion(
            spy,
            title=" Chop week ",
            thesis="leaders  hold the 50 day",
            backtests=["NVDA swing_pullback, n=7, avg +0.41R", " "],
            next_day_setup=["AVGO above 340"],
        )
    )
    assert out.startswith("Saved trading discussion #ab12cd")
    assert spy.calls == [
        (
            "save_trading_discussion",
            {
                "title": "Chop week",
                "backtests": ["NVDA swing_pullback, n=7, avg +0.41R"],
                "next_day_setup": ["AVGO above 340"],
                "thesis": "leaders hold the 50 day",
            },
        )
    ]
    spy.calls.clear()
    assert "Give me a title" in asyncio.run(handle_save_trading_discussion(spy, title=""))
    assert spy.calls == []
    asyncio.run(
        handle_save_trading_discussion(
            spy,
            title="Chop week",
            skip_symbols=["amd", " "],
            focus_symbols=["avgo"],
            risk_scale=0.5,
            stand_down=False,
            fallback=False,
            rule_change="try  a 3R target",
        )
    )
    assert spy.calls == [
        (
            "save_trading_discussion",
            {
                "title": "Chop week",
                "rule_change": "try a 3R target",
                "skip_symbols": ["AMD"],
                "focus_symbols": ["AVGO"],
                "risk_scale": 0.5,
                "fallback": False,
            },
        )
    ]
