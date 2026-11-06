"""Voice strategy approval reaches the model, including the bare "yes" after the read-back."""

from __future__ import annotations

import asyncio

from sam_worker.tools.select import STRATEGY_APPROVE_TOOLS, VOICE_TOOLS, select_tools_for_utterance


def test_approve_and_undo_are_voice_tools() -> None:
    assert set(STRATEGY_APPROVE_TOOLS) <= set(VOICE_TOOLS)


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
