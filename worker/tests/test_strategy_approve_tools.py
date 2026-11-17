"""Voice strategy approval reaches the model, including the bare "yes" after the read-back."""

from __future__ import annotations

import asyncio
import json

import httpx

from sam_worker.tools.rainmaker import HttpRainmakerClient
from sam_worker.tools.rainmaker_registry import _OWNER_REFUSAL, register_rainmaker_tools
from sam_worker.tools.registry import ToolRegistry
from sam_worker.tools.select import STRATEGY_APPROVE_TOOLS, VOICE_TOOLS, select_tools_for_utterance

RM_BASE = "https://rm-api.test"
RM_TOKEN = "cron-secret"


def test_approve_and_undo_are_voice_tools() -> None:
    assert set(STRATEGY_APPROVE_TOOLS) <= set(VOICE_TOOLS)


def test_owner_phrases_for_a_trade_idea_select_test_idea() -> None:
    for said in ("test a new trade idea", "I want you to backtest an idea"):
        assert "test_idea" in select_tools_for_utterance(said), said


def test_approve_words_select_both_tools() -> None:
    for said in ("Approve the late Warrior strategy", "undo that approval", "take it back"):
        tools = select_tools_for_utterance(said)
        assert "approve_strategy" in tools and "undo_strategy" in tools, said


def test_bare_yes_alone_does_not_select_approve() -> None:
    assert "approve_strategy" not in select_tools_for_utterance("yes")


def test_yes_after_read_back_keeps_approve_one_turn() -> None:
    from livekit.agents import Agent
    from livekit.agents.llm import ChatContext

    from sam_worker.router import FastIntentRouter, RoutedSamuelAgent

    seen: list[list[str]] = []

    def fake_parent(self, chat_ctx, tools, model_settings):
        seen.append([getattr(tool, "__name__", "") for tool in (tools or [])])
        return "ok"

    async def direct(_decision):
        raise AssertionError("approval must reach the model")

    async def publish(_command):
        return None

    class _Tool:
        def __init__(self, name: str) -> None:
            self.__name__ = name

    tools = [_Tool(name) for name in ("approve_strategy", "undo_strategy", "get_pulse", "run_command")]
    original = Agent.llm_node
    Agent.llm_node = fake_parent
    try:
        agent = RoutedSamuelAgent(
            router=FastIntentRouter(), direct_execute=direct, publish_command=publish, instructions="test"
        )
        for said in ("Approve the late Warrior strategy", "yes", "yes"):
            context = ChatContext.empty()
            context.add_message(role="user", content=said)
            asyncio.run(agent.llm_node(context, tools, None))
    finally:
        Agent.llm_node = original
    assert "approve_strategy" in seen[0]
    assert "approve_strategy" in seen[1]
    assert "approve_strategy" not in seen[2]


# ---- registry tool -> handler -> HttpRainmakerClient -> rm_api POST /samuel/tool ----------------

def _strategy_tool(name: str, reply: dict, *, owner: bool = True):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if (request.method, request.url.path) != ("POST", "/samuel/tool"):
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(200, json=reply)

    registry = ToolRegistry()
    register_rainmaker_tools(registry)
    client = HttpRainmakerClient(
        RM_BASE, RM_TOKEN, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    tools = registry.build_livekit_tools(
        client, lambda: owner, function_tool=lambda fn: fn, owner_refusal=_OWNER_REFUSAL, only=[name]
    )
    return tools[0], requests


def _sent(requests: list[httpx.Request]) -> dict:
    assert len(requests) == 1
    assert requests[0].headers.get("X-RM-CRON-TOKEN") == RM_TOKEN
    return json.loads(requests[0].content)


def test_strategy_tools_are_owner_only_writes() -> None:
    registry = ToolRegistry()
    register_rainmaker_tools(registry)
    specs = {s.name: s for s in registry.specs()}
    for name in ("test_idea", "approve_strategy", "undo_strategy"):
        assert not specs[name].read_only, name
        assert specs[name].requires_approval, name
        assert "Owner only" in specs[name].description, name
    assert "read its name back" in specs["approve_strategy"].description
    assert "Reply UNDO <code> within 10 minutes" in specs["approve_strategy"].description


def test_test_idea_posts_words_and_test() -> None:
    said = "Got it. Testing your idea. Answer Monday."
    tool, requests = _strategy_tool("test_idea", {"ok": True, "name": "test_idea", "text": said})
    out = asyncio.run(tool(None, "move the stop to break even at 1R", "be_1r"))
    assert _sent(requests) == {
        "name": "test_idea",
        "args": {"words": "move the stop to break even at 1R", "test": "be_1r"},
    }
    assert out == said


def test_approve_strategy_speaks_rm_api_undo_line() -> None:
    said = (
        "Approved AB12CD: Warrior late entry can trade live. This was not a trade. "
        "Reply UNDO AB12CD within 10 minutes to take it back."
    )
    tool, requests = _strategy_tool("approve_strategy", {"ok": True, "name": "approve_strategy", "text": said})
    out = asyncio.run(tool(None, "h001_warrior_late"))
    assert _sent(requests) == {"name": "approve_strategy", "args": {"strategy_id": "h001_warrior_late"}}
    assert out == said


def test_approve_strategy_without_open_offer_relays_refusal() -> None:
    said = "There is no open approval for that strategy."
    tool, requests = _strategy_tool("approve_strategy", {"ok": True, "name": "approve_strategy", "text": said})
    out = asyncio.run(tool(None, "swing_pullback_wide"))
    assert _sent(requests)["args"] == {"strategy_id": "swing_pullback_wide"}
    assert out == said


def test_undo_strategy_posts_code() -> None:
    said = "Undid AB12CD. h001_warrior_late is not live."
    tool, requests = _strategy_tool("undo_strategy", {"ok": True, "name": "undo_strategy", "text": said})
    out = asyncio.run(tool(None, "AB12CD"))
    assert _sent(requests) == {"name": "undo_strategy", "args": {"code": "AB12CD"}}
    assert out == said


def test_rm_api_down_is_honest() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    registry = ToolRegistry()
    register_rainmaker_tools(registry)
    client = HttpRainmakerClient(
        RM_BASE, RM_TOKEN, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    tool = registry.build_livekit_tools(
        client, lambda: True, function_tool=lambda fn: fn, owner_refusal=_OWNER_REFUSAL, only=["approve_strategy"]
    )[0]
    assert asyncio.run(tool(None, "h001_warrior_late")) == "I couldn't do that right now."


def test_strategy_tools_refuse_non_owner_without_calling_rm_api() -> None:
    for name, args in (
        ("test_idea", ("words", "be_1r")),
        ("approve_strategy", ("h001_warrior_late",)),
        ("undo_strategy", ("AB12CD",)),
    ):
        tool, requests = _strategy_tool(name, {"ok": True, "text": "should not run"}, owner=False)
        assert asyncio.run(tool(None, *args)) == _OWNER_REFUSAL, name
        assert requests == [], name
