from __future__ import annotations

import asyncio

from livekit.agents import NOT_GIVEN, ModelSettings
from livekit.agents.llm import ChatContext, FunctionCall, FunctionCallOutput

from sam_worker.router import (
    DirectResult,
    FastIntentRouter,
    RoutedSamuelAgent,
    _render_memory_row,
    _safe_utterance_for_log,
)
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


def test_canonical_memory_rows_preserve_surface_provenance() -> None:
    rendered = _render_memory_row(
        {
            "content": "Cathy prefers morning meetings.",
            "provenance": {"surface": "sms"},
        }
    )
    assert rendered == "[sms] Cathy prefers morning meetings."


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
    assert _safe_utterance_for_log("add another\nappointment") == "add another appointment"


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


def test_llm_node_attaches_no_tools_for_pricing() -> None:
    seen: dict[str, list[str]] = {}

    def fake_parent(self, chat_ctx, tools, model_settings):
        seen["tools"] = [getattr(tool, "__name__", "") for tool in (tools or [])]
        return "priced"

    async def direct(_decision):
        raise AssertionError("pricing must not direct-route")

    async def publish(_command):
        return None

    class _Tool:
        def __init__(self, name: str) -> None:
            self.__name__ = name

    from livekit.agents import Agent

    original = Agent.llm_node
    Agent.llm_node = fake_parent
    try:
        agent = RoutedSamuelAgent(
            router=FastIntentRouter(),
            direct_execute=direct,
            publish_command=publish,
            instructions="test",
        )
        context = ChatContext.empty()
        context.add_message(role="user", content="How much does Rainmaker cost per month?")
        tools = [_Tool("get_pulse"), _Tool("get_scans"), _Tool("list_studio_runs")]
        result = asyncio.run(agent.llm_node(context, tools, None))
    finally:
        Agent.llm_node = original
    assert result == "priced"
    assert seen["tools"] == []


def test_empty_tool_subset_clears_incompatible_tool_choice() -> None:
    seen: dict[str, object] = {}

    def fake_parent(self, chat_ctx, tools, model_settings):
        seen["tools"] = list(tools or [])
        seen["tool_choice"] = model_settings.tool_choice
        return "ok"

    async def direct(_decision):
        raise AssertionError

    async def publish(_command):
        return None

    from livekit.agents import Agent

    original = Agent.llm_node
    Agent.llm_node = fake_parent
    try:
        agent = RoutedSamuelAgent(
            router=FastIntentRouter(),
            direct_execute=direct,
            publish_command=publish,
            instructions="test",
        )
        context = ChatContext.empty()
        context.add_message(role="user", content="Tell me a short story")
        result = asyncio.run(
            agent.llm_node(context, [], ModelSettings(tool_choice="none"))
        )
    finally:
        Agent.llm_node = original
    assert result == "ok"
    assert seen["tools"] == []
    assert seen["tool_choice"] is NOT_GIVEN


def test_stable_full_flag_keeps_complete_tool_schema_set() -> None:
    seen: dict[str, object] = {}

    def fake_parent(self, chat_ctx, tools, model_settings):
        seen["tools"] = [getattr(tool, "__name__", "") for tool in tools]
        return "ok"

    async def direct(_decision):
        raise AssertionError

    async def publish(_command):
        return None

    class _Tool:
        def __init__(self, name: str) -> None:
            self.__name__ = name

    from livekit.agents import Agent

    original = Agent.llm_node
    Agent.llm_node = fake_parent
    try:
        agent = RoutedSamuelAgent(
            router=FastIntentRouter(),
            direct_execute=direct,
            publish_command=publish,
            use_full_tool_set=True,
            instructions="test",
        )
        context = ChatContext.empty()
        context.add_message(role="user", content="How much does Rainmaker cost?")
        tools = [_Tool("get_pulse"), _Tool("propose_calendar_change")]
        result = asyncio.run(agent.llm_node(context, tools, ModelSettings()))
    finally:
        Agent.llm_node = original
    assert result == "ok"
    assert seen["tools"] == ["get_pulse", "propose_calendar_change"]


def test_calendar_turn_requires_the_selected_tool_call() -> None:
    seen: dict[str, object] = {}

    def fake_parent(self, chat_ctx, tools, model_settings):
        seen["tools"] = [getattr(tool, "__name__", "") for tool in (tools or [])]
        seen["tool_choice"] = model_settings.tool_choice
        seen["developer"] = [
            str(message.text_content or "")
            for message in chat_ctx.messages()
            if message.role == "developer"
        ]
        return "calendar"

    async def direct(_decision):
        raise AssertionError("calendar changes must use the LLM tool path")

    async def publish(_command):
        return None

    class _Tool:
        def __init__(self, name: str) -> None:
            self.__name__ = name

    from livekit.agents import Agent

    original = Agent.llm_node
    Agent.llm_node = fake_parent
    calendar_turn_state: dict[str, object] = {}
    try:
        agent = RoutedSamuelAgent(
            router=FastIntentRouter(),
            direct_execute=direct,
            publish_command=publish,
            calendar_turn_state=calendar_turn_state,
            instructions="test",
        )
        context = ChatContext.empty()
        context.add_message(
            role="user",
            content="Move Samuel scheduling proof to Wednesday at four",
        )
        tools = [
            _Tool("get_calendar_events"),
            _Tool("propose_calendar_change"),
            _Tool("commit_calendar_change"),
        ]
        result = asyncio.run(
            agent.llm_node(context, tools, ModelSettings(tool_choice="auto"))
        )
        initial_tools = seen["tools"]
        initial_tool_choice = seen["tool_choice"]
        context.insert(
            [
                FunctionCall(
                    call_id="calendar-1",
                    arguments='{"action":"update"}',
                    name="propose_calendar_change",
                ),
                FunctionCallOutput(
                    call_id="calendar-1",
                    name="propose_calendar_change",
                    output="Update the event to four? Say yes to confirm.",
                    is_error=False,
                ),
            ]
        )
        followup = asyncio.run(
            agent.llm_node(context, tools, ModelSettings(tool_choice="auto"))
        )
    finally:
        Agent.llm_node = original
    assert result == "calendar"
    assert followup == "Update the event to four? Say yes to confirm."
    assert initial_tools == [
        "get_calendar_events",
        "propose_calendar_change",
        "commit_calendar_change",
    ]
    assert initial_tool_choice == "auto"
    assert seen["tools"] == initial_tools
    assert seen["tool_choice"] == "auto"
    assert any(
        "action='update'" in message for message in seen["developer"]
    )
    assert calendar_turn_state["action"] == "update"
    assert calendar_turn_state["preserve_duration"] is True


def test_yes_or_no_does_not_force_a_tool_call() -> None:
    seen: dict[str, object] = {}

    def fake_parent(self, chat_ctx, tools, model_settings):
        seen["tools"] = [getattr(tool, "__name__", "") for tool in (tools or [])]
        seen["tool_choice"] = model_settings.tool_choice
        return "ask"

    async def direct(_decision):
        raise AssertionError

    async def publish(_command):
        return None

    class _Tool:
        def __init__(self, name: str) -> None:
            self.__name__ = name

    from livekit.agents import Agent

    original = Agent.llm_node
    Agent.llm_node = fake_parent
    try:
        agent = RoutedSamuelAgent(
            router=FastIntentRouter(),
            direct_execute=direct,
            publish_command=publish,
            instructions="test",
        )
        context = ChatContext.empty()
        context.add_message(role="user", content="Yes or no?")
        tools = [
            _Tool("get_calendar_events"),
            _Tool("propose_calendar_change"),
            _Tool("commit_calendar_change"),
        ]
        result = asyncio.run(
            agent.llm_node(context, tools, ModelSettings(tool_choice="required"))
        )
    finally:
        Agent.llm_node = original
    assert result == "ask"
    assert seen["tool_choice"] == "auto"


def test_yes_commits_without_the_llm() -> None:
    async def direct(_decision):
        raise AssertionError

    async def publish(_command):
        return None

    async def commit() -> str:
        return "Booked. Saturday at 3pm."

    class _Tool:
        def __init__(self, name: str) -> None:
            self.__name__ = name

    from livekit.agents import Agent

    original = Agent.llm_node
    Agent.llm_node = lambda *args, **kwargs: "llm"  # noqa: ARG005
    try:
        agent = RoutedSamuelAgent(
            router=FastIntentRouter(),
            direct_execute=direct,
            publish_command=publish,
            calendar_commit=commit,
            instructions="test",
        )
        context = ChatContext.empty()
        context.add_message(role="user", content="Yes.")
        tools = [_Tool("commit_calendar_change")]
        result = asyncio.run(
            agent.llm_node(context, tools, ModelSettings(tool_choice="required"))
        )
    finally:
        Agent.llm_node = original
    assert result == "Booked. Saturday at 3pm."


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
