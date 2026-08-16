from __future__ import annotations

import asyncio

from livekit.agents.llm import ChatContext

from sam_worker.router import DirectResult, FastIntentRouter, RoutedSamuelAgent
from sam_worker.tool_latency import ToolLatencyManager


class _Context:
    def __init__(self) -> None:
        self.fillers: list[str] = []
        self.updates: list[str] = []

    def with_filler(self, source, **_kwargs):
        parent = self

        class _Filler:
            async def __aenter__(self):
                parent.fillers.append(source)

            async def __aexit__(self, *_args):
                return False

        return _Filler()

    def update(self, message: str) -> None:
        self.updates.append(message)


def test_router_is_high_confidence_and_fails_complex_to_llm() -> None:
    router = FastIntentRouter()
    assert router.classify("What time is it?").route == "time"
    assert router.classify("Open the Rainmaker dashboard").route == "open_dashboard"
    assert router.classify("Check Rainmaker pulse").route == "rainmaker_pulse"
    assert router.classify("What is the market pulse right now?").route == "rainmaker_pulse"
    assert router.classify("What are today's top scans?").route == "rainmaker_scans"
    assert router.classify("Read my brief.").route == "rainmaker_brief"
    assert router.classify("What is my account balance and open P&L?").route == "rainmaker_trades"
    assert router.classify("What did I queue in research yesterday?").route == "rainmaker_research"
    assert router.classify("How much does Rainmaker cost per month?").direct is False
    complex_route = router.classify("Explain whether I should buy NVDA right now")
    assert complex_route.direct is False
    assert complex_route.route == "llm"


def test_scan_route_executes_named_tool() -> None:
    class _Client:
        async def get_scans(self, limit: int = 5):
            return {"ok": True, "symbols": ["NVDA", "AAPL"]}

    router = FastIntentRouter()
    decision = router.classify("What are today's top scans?")
    result = asyncio.run(router.execute(decision, rainmaker_client=_Client()))
    assert decision.route == "rainmaker_scans"
    assert result.tool_name == "get_scans"
    assert "NVDA" in result.spoken


def test_time_route_executes_without_client() -> None:
    router = FastIntentRouter()
    result = asyncio.run(router.execute(router.classify("current time"), rainmaker_client=None))
    assert result.spoken.startswith("It is ")
    assert result.command is None


def test_direct_route_bypasses_primary_llm_node() -> None:
    calls = []

    async def direct(decision):
        calls.append(decision.route)
        return DirectResult("Direct answer.")

    async def publish(_command):
        return None

    agent = RoutedSamuelAgent(
        router=FastIntentRouter(),
        direct_execute=direct,
        publish_command=publish,
        instructions="test",
    )
    context = ChatContext.empty()
    context.add_message(role="user", content="What time is it?")
    result = asyncio.run(agent.llm_node(context, [], None))
    assert result == "Direct answer."
    assert calls == ["time"]


def test_read_only_tool_retries_then_caches() -> None:
    calls = 0
    timings = []

    async def flaky(_context):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError
        return "ready"

    manager = ToolLatencyManager(
        on_timing=lambda name, elapsed, cached: timings.append((name, elapsed, cached))
    )
    wrapped = manager.wrap(
        name="get_pulse",
        read_only=True,
        requires_approval=False,
        handler=flaky,
    )
    context = _Context()
    assert asyncio.run(wrapped(context)) == "ready"
    assert asyncio.run(wrapped(context)) == "ready"
    assert calls == 2
    assert context.fillers == ["Checking that now."]
    assert timings[0][0] == "get_pulse" and timings[0][2] is False
    assert timings[1] == ("get_pulse", 0.0, True)


def test_trigger_tool_is_never_retried_or_cached() -> None:
    calls = 0

    async def fails(_context):
        nonlocal calls
        calls += 1
        raise RuntimeError("no")

    manager = ToolLatencyManager()
    wrapped = manager.wrap(
        name="send_brief",
        read_only=False,
        requires_approval=True,
        handler=fails,
    )
    context = _Context()
    expected = "That action did not finish. I did not retry it."
    assert asyncio.run(wrapped(context)) == expected
    assert asyncio.run(wrapped(context)) == expected
    assert calls == 2
