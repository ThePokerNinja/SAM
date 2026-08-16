# -*- coding: utf-8 -*-
"""SAM-035: shared tool registry - schema, handler, read_only, requires_approval."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

ToolBuilder = Callable[[Any, Callable[[], bool], dict[str, Any]], Callable[..., Awaitable[str]]]


@dataclass(frozen=True)
class ToolSpec:
    """Metadata for one Samuel tool (skill-pack manifests reference ``name``)."""

    name: str
    description: str
    read_only: bool
    requires_approval: bool


class ToolRegistry:
    """In-memory catalog of tool specs + builders bound at session start."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._builders: dict[str, ToolBuilder] = {}

    def register(self, spec: ToolSpec, builder: ToolBuilder) -> None:
        if spec.name in self._specs:
            raise ValueError(f"tool already registered: {spec.name}")
        self._specs[spec.name] = spec
        self._builders[spec.name] = builder

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return list(self._specs.keys())

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def subset(self, names: list[str]) -> ToolRegistry:
        """Return a registry view containing only the named tools (order preserved)."""
        out = ToolRegistry()
        for name in names:
            spec = self._specs.get(name)
            builder = self._builders.get(name)
            if spec is None or builder is None:
                raise KeyError(f"unknown tool: {name}")
            out._specs[name] = spec
            out._builders[name] = builder
        return out

    def build_livekit_tools(
        self,
        client: Any,
        is_owner: Callable[[], bool],
        *,
        function_tool: Callable[[Callable[..., Awaitable[str]]], Any],
        owner_refusal: str,
        deps: dict[str, Any] | None = None,
        only: list[str] | None = None,
    ) -> list[Any]:
        """Materialize registered tools as LiveKit function_tool callables."""
        names = only if only is not None else self.names()
        deps = deps or {}
        tools: list[Any] = []
        for name in names:
            spec = self._specs[name]
            builder = self._builders[name]
            raw = builder(client, is_owner, deps)
            latency_manager = deps.get("tool_latency_manager")
            if latency_manager is not None:
                raw = latency_manager.wrap(
                    name=spec.name,
                    read_only=spec.read_only,
                    requires_approval=spec.requires_approval,
                    handler=raw,
                )

            if spec.requires_approval:
                original = raw

                async def _gated(context: Any, _orig=original) -> str:
                    if not is_owner():
                        return owner_refusal
                    return await _orig(context)

                raw = _gated

            raw.__doc__ = spec.description
            raw.__name__ = spec.name
            tools.append(function_tool(raw))
        return tools
