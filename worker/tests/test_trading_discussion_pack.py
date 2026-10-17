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
    # The 2026-10-17 calls: the flag was set but gpt-4o-mini never asked the question.
    session = build_session(session_id="call-_+18318186191_x", surface="phone")
    session.room_name = "call-_+18318186191_x"
    first = "Yeah. Let's talk trades."
    # Preemptive generation asks before the session sees the turn; the re-run after it asks the same.
    assert session.trading_offer_for(first, is_owner=True) == TRADING_OFFER_LINE == "Start a trading discussion?"
    session.activate_from_utterance(first)
    assert session.trading_offer_for(first, is_owner=True) == TRADING_OFFER_LINE
    second = "Yeah. I wanna back test NVIDIA on the swing rule."
    assert session.trading_offer_for(second, is_owner=True) is None
    assert session.activate_from_utterance(second) is True
    assert session.kind == "trading_discussion"
    assert session.trading_offer_for("backtest AVGO too", is_owner=True) is None
    assert session.trading_offer_for(first, is_owner=False) is None
    assert build_session(session_id="p", surface="portal").trading_offer_for("start a trading discussion", is_owner=True) is None


def test_llm_node_speaks_the_offer_even_when_called_before_the_turn_hook() -> None:
    from livekit.agents import ChatContext

    from sam_worker.router import FastIntentRouter, RoutedSamuelAgent

    async def direct(_decision):
        raise AssertionError("no direct route")

    async def publish(_command):
        return None

    session = build_session(session_id="call-_+18318186191_z", surface="phone")
    session.room_name = "call-_+18318186191_z"
    agent = RoutedSamuelAgent(
        router=FastIntentRouter(),
        direct_execute=direct,
        publish_command=publish,
        reply_override=lambda text: session.trading_offer_for(text, is_owner=True),
        instructions="test",
    )
    ctx = ChatContext.empty()
    ctx.add_message(role="user", content="Let's talk trades.")
    assert asyncio.run(agent.llm_node(ctx, [], None)) == "Start a trading discussion?"
    # A pending override from an earlier utterance never answers a later one.
    agent._pending_override = ("Let's talk trades.", "stale")
    session.activate_from_utterance("Let's talk trades.")
    session.activate_from_utterance("Yes.")
    ctx.add_message(role="user", content="Yes.")
    from livekit.agents import Agent

    original = Agent.llm_node

    def fake(self, chat_ctx, tools, model_settings):
        return "llm"

    Agent.llm_node = fake
    try:
        assert asyncio.run(agent.llm_node(ctx, [], None)) == "llm"
    finally:
        Agent.llm_node = original


def test_phone_mishearings_still_earn_the_offer_and_plans_reach_save() -> None:
    # 2026-10-17 call: STT heard "Let's talk trades" as "Stock trades." and the plan had no save tool.
    session = build_session(session_id="call-_+18318186191_q", surface="phone")
    session.room_name = "call-_+18318186191_q"
    assert session.trading_offer_for("Stock trades.", is_owner=True) == TRADING_OFFER_LINE
    assert "save_trading_discussion" in select_tools_for_utterance("Skip AMD tomorrow.")
    assert "save_trading_discussion" in select_tools_for_utterance("focus on AVGO and stand down after that")


def test_backtest_utterances_go_straight_to_the_tool() -> None:
    from sam_worker.router import FastIntentRouter

    router = FastIntentRouter()
    for said, sym in (
        ("Back test NVIDIA on the swing roll.", "nvidia"),
        ("Yeah. I wanna back test NVIDIA on the swing rule.", "nvidia"),
        ("backtest AVGO", "avgo"),
        ("Can you run a backtest on Palo Alto?", "palo alto"),
        ("Backtest N V D A for me please", "n v d a"),
    ):
        decision = router.classify(said)
        assert (decision.route, decision.direct, decision.arg) == ("rainmaker_backtest", True, sym), said
    for said in ("backtest it", "backtest that again", "what did the backtest say", "backtest NVDA on orh"):
        assert router.classify(said).route != "rainmaker_backtest", said

    class Spy(MockRainmakerClient):
        calls: list = []

        async def run_tool(self, name, args=None):
            self.calls.append((name, dict(args or {})))
            return {"ok": True, "text": "NVDA swing pullback, 2025-08-13 to 2026-10-16: 9 trades"}

    spy = Spy()
    result = asyncio.run(router.execute(router.classify("Back test NVIDIA on the swing roll."), rainmaker_client=spy))
    assert result.spoken.startswith("NVDA swing pullback") and result.tool_name == "run_backtest"
    assert spy.calls == [("run_backtest", {"symbol": "nvidia", "rule": "swing_pullback"})]


def test_a_trading_call_never_opens_a_proposal_notebook_at_hang_up() -> None:
    # 2026-10-17: two trading calls each texted the Izakaya proposal link afterwards.
    from sam_worker.agent import post_call_notebook_text

    assert post_call_notebook_text("", "") == ""
    assert post_call_notebook_text("", "   ") == ""
    assert post_call_notebook_text("", "izakaya site with reservations") == "izakaya site with reservations"
    assert post_call_notebook_text("eng-1", "anything") == ""


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
