"""SAM-035: shared tool registry - registration, flags, owner gate, subset."""

from __future__ import annotations

import asyncio
import inspect
import unittest
from typing import Any, get_type_hints

from livekit.agents import RunContext

from sam_worker.tools.rainmaker_registry import register_rainmaker_tools
from sam_worker.tools.registry import ToolRegistry, ToolSpec


def _identity_decorator(fn: Any) -> Any:
    return fn


class RegistryMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        register_rainmaker_tools(self.registry)

    def test_registers_rainmaker_tools(self) -> None:
        self.assertEqual(len(self.registry.names()), 19)

    def test_read_only_tools(self) -> None:
        read_only = {s.name for s in self.registry.specs() if s.read_only}
        self.assertEqual(
            read_only,
            {
                "get_scans",
                "get_pulse",
                "get_trades",
                "get_research",
                "get_brief",
                "list_studio_runs",
                "studio_asset_status",
                "studio_campaign_report",
                "get_calendar_events",
                "list_captures",
            },
        )

    def test_requires_approval_tools(self) -> None:
        gated = {s.name for s in self.registry.specs() if s.requires_approval}
        self.assertEqual(
            gated,
            {
                "run_scan",
                "queue_research",
                "send_brief",
                "send_hero",
                "commit_calendar_change",
                "capture_note",
            },
        )

    def test_duplicate_register_raises(self) -> None:
        reg = ToolRegistry()
        spec = ToolSpec(name="x", description="d", read_only=True, requires_approval=False)

        async def _noop(_ctx: Any) -> str:
            return "ok"

        reg.register(spec, lambda _c, _o, _d: _noop)
        with self.assertRaises(ValueError):
            reg.register(spec, lambda _c, _o, _d: _noop)

    def test_subset_preserves_order(self) -> None:
        sub = self.registry.subset(["get_pulse", "get_scans"])
        self.assertEqual(sub.names(), ["get_pulse", "get_scans"])


class RegistryBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        register_rainmaker_tools(self.registry)
        self.owner_refusal = "owner only"

    def test_build_livekit_tools_count(self) -> None:
        tools = self.registry.build_livekit_tools(
            client=object(),
            is_owner=lambda: True,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
        )
        self.assertEqual(len(tools), 19)

    def test_calendar_proposal_schema_only_requires_action(self) -> None:
        tools = self.registry.build_livekit_tools(
            client=object(),
            is_owner=lambda: True,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
            only=["propose_calendar_change"],
        )
        params = inspect.signature(tools[0]).parameters
        self.assertIs(params["action"].default, inspect.Parameter.empty)
        for name in (
            "summary",
            "start",
            "end",
            "duration_minutes",
            "event_id",
            "event_query",
            "description",
            "location",
            "all_day",
            "timezone",
        ):
            self.assertIsNone(params[name].default)

    def test_calendar_turn_state_overrides_conflicting_model_action(self) -> None:
        seen: dict[str, Any] = {}
        turn_state = {
            "action": "update",
            "preserve_duration": True,
        }

        class Spy:
            async def propose_calendar_change(self, **fields: Any) -> dict:
                seen.update(fields)
                return {
                    "ok": True,
                    "proposal": {"proposal_id": "p1", "readback": "Move event?"},
                }

        tools = self.registry.build_livekit_tools(
            client=Spy(),
            is_owner=lambda: True,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
            deps={
                "session_id": "call-move",
                "calendar_turn_state": turn_state,
            },
            only=["propose_calendar_change"],
        )
        asyncio.run(
            tools[0](
                None,
                "create",
                summary="Samuel scheduling proof",
                start="2026-08-19T16:00:00-07:00",
                end="2026-08-19T17:00:00-07:00",
                duration_minutes=60,
            )
        )
        self.assertEqual(seen["action"], "update")
        self.assertIsNone(seen["end"])
        self.assertIsNone(seen["duration_minutes"])
        self.assertIs(seen["preserve_duration"], True)
        self.assertIs(turn_state["completed"], True)

    def test_owner_gate_blocks_trigger_tool(self) -> None:
        tools = self.registry.build_livekit_tools(
            client=object(),
            is_owner=lambda: False,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
            only=["run_scan"],
        )
        out = asyncio.run(tools[0](None))
        self.assertEqual(out, self.owner_refusal)

    def test_owner_gate_preserves_multi_argument_signature(self) -> None:
        class Spy:
            async def queue_research(self, prompt: str) -> dict:
                return {"ok": True, "shortId": "abc", "queuedAhead": 0}

        tools = self.registry.build_livekit_tools(
            client=Spy(),
            is_owner=lambda: True,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
            only=["queue_research"],
        )
        self.assertEqual(
            list(inspect.signature(tools[0]).parameters), ["context", "topic"]
        )
        self.assertIs(get_type_hints(tools[0])["context"], RunContext)
        out = asyncio.run(tools[0](None, "NVDA earnings"))
        self.assertIn("Queued your research", out)

    def test_owner_gate_blocks_multi_argument_tool(self) -> None:
        class Spy:
            async def queue_research(self, prompt: str) -> dict:
                raise AssertionError("owner-gated handler must not execute")

        tools = self.registry.build_livekit_tools(
            client=Spy(),
            is_owner=lambda: False,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
            only=["queue_research"],
        )
        out = asyncio.run(tools[0](None, "NVDA earnings"))
        self.assertEqual(out, self.owner_refusal)

    def test_owner_gate_blocks_non_owner_calendar_commit(self) -> None:
        class Spy:
            async def commit_calendar_change(
                self, session_id: str, proposal_id: str = ""
            ) -> dict:
                raise AssertionError("calendar commit must not execute")

        tools = self.registry.build_livekit_tools(
            client=Spy(),
            is_owner=lambda: False,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
            deps={"session_id": "hostile-caller"},
            only=["commit_calendar_change"],
        )
        out = asyncio.run(tools[0](None, "pending-proposal"))
        self.assertEqual(out, self.owner_refusal)

    def test_builder_invokes_handler(self) -> None:
        class Spy:
            async def get_scans(self, limit: int = 10) -> dict:
                return {"ok": True, "symbols": ["AAPL"], "newSymbols": []}

        tools = self.registry.build_livekit_tools(
            client=Spy(),
            is_owner=lambda: True,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
            only=["get_scans"],
        )
        out = asyncio.run(tools[0](None))
        self.assertIn("AAPL", out)

    def test_run_scan_fires_background_task(self) -> None:
        fired: list[Any] = []

        async def bg(client: Any) -> None:
            fired.append(client)

        async def exercise() -> None:
            tools = self.registry.build_livekit_tools(
                client=object(),
                is_owner=lambda: True,
                function_tool=_identity_decorator,
                owner_refusal=self.owner_refusal,
                deps={"run_scan_bg": bg},
                only=["run_scan"],
            )
            out = await tools[0](None)
            self.assertIn("Scan started", out)
            await asyncio.sleep(0.01)

        asyncio.run(exercise())
        self.assertEqual(len(fired), 1)


if __name__ == "__main__":
    unittest.main()
