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

    def test_registers_nine_rainmaker_tools(self) -> None:
        self.assertEqual(len(self.registry.names()), 9)

    def test_read_only_tools(self) -> None:
        read_only = {s.name for s in self.registry.specs() if s.read_only}
        self.assertEqual(
            read_only,
            {"get_scans", "get_pulse", "get_trades", "get_research", "get_brief"},
        )

    def test_requires_approval_tools(self) -> None:
        gated = {s.name for s in self.registry.specs() if s.requires_approval}
        self.assertEqual(
            gated,
            {"run_scan", "queue_research", "send_brief", "send_hero"},
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
        self.assertEqual(len(tools), 9)

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

    def test_owner_gate_exposes_only_context_parameter(self) -> None:
        tools = self.registry.build_livekit_tools(
            client=object(),
            is_owner=lambda: True,
            function_tool=_identity_decorator,
            owner_refusal=self.owner_refusal,
            only=["run_scan"],
        )
        self.assertEqual(list(inspect.signature(tools[0]).parameters), ["context"])
        self.assertIs(get_type_hints(tools[0])["context"], RunContext)

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
