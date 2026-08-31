"""Concurrent context assembly kept off the realtime critical path (SAM-065)."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

Provider = Callable[[], Any | Awaitable[Any]]


@dataclass
class ContextSnapshot:
    memory: Any = field(default_factory=list)
    profile: Any = field(default_factory=dict)
    tools: Any = field(default_factory=list)
    permissions: Any = field(default_factory=dict)
    external: Any = field(default_factory=dict)
    session_summary: str = ""
    timings_ms: dict[str, float] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total_ms(self) -> float:
        return max(self.timings_ms.values(), default=0.0)


async def _call(name: str, provider: Provider) -> tuple[str, Any, float, str | None]:
    started = time.perf_counter()
    try:
        value = provider()
        if inspect.isawaitable(value):
            value = await value
        elapsed = (time.perf_counter() - started) * 1000.0
        return name, value, elapsed, None
    except Exception as exc:  # noqa: BLE001 - context providers degrade independently
        elapsed = (time.perf_counter() - started) * 1000.0
        return name, None, elapsed, type(exc).__name__


async def assemble_context(
    *,
    memory: Provider,
    profile: Provider,
    tools: Provider,
    permissions: Provider,
    external: Provider | None = None,
    timeout_s: float = 0.75,
) -> ContextSnapshot:
    """Run independent lookups concurrently and return partial context on failure."""
    providers: dict[str, Provider] = {
        "memory": memory,
        "profile": profile,
        "tools": tools,
        "permissions": permissions,
    }
    if external is not None:
        providers["external"] = external

    tasks = [asyncio.create_task(_call(name, provider)) for name, provider in providers.items()]
    try:
        rows = await asyncio.wait_for(asyncio.gather(*tasks), timeout=max(0.01, timeout_s))
    except asyncio.TimeoutError:
        for task in tasks:
            if not task.done():
                task.cancel()
        rows = []
        for name, task in zip(providers, tasks, strict=True):
            if task.done() and not task.cancelled():
                try:
                    rows.append(task.result())
                except Exception:  # noqa: BLE001
                    rows.append((name, None, timeout_s * 1000.0, "ProviderError"))
            else:
                rows.append((name, None, timeout_s * 1000.0, "TimeoutError"))

    snapshot = ContextSnapshot()
    for name, value, elapsed, error in rows:
        snapshot.timings_ms[name] = round(elapsed, 3)
        if error:
            snapshot.errors[name] = error
            continue
        setattr(snapshot, name, value)
    return snapshot
