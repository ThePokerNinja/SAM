"""Non-blocking tool execution policy (SAM-066)."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger("sam.tools.latency")


@dataclass(frozen=True)
class ToolPolicy:
    timeout_s: float
    retries: int
    cache_ttl_s: float
    fallback: str


@dataclass
class _CacheEntry:
    expires_at: float
    value: str


class ToolLatencyManager:
    def __init__(
        self,
        on_timing: Callable[[str, float, bool], None] | None = None,
    ) -> None:
        self._cache: dict[str, _CacheEntry] = {}
        self._on_timing = on_timing

    @staticmethod
    def policy(*, read_only: bool, requires_approval: bool) -> ToolPolicy:
        if read_only and not requires_approval:
            return ToolPolicy(
                timeout_s=8.0,
                retries=1,
                cache_ttl_s=15.0,
                fallback="That lookup is taking too long. I can try it again.",
            )
        return ToolPolicy(
            timeout_s=45.0,
            retries=0,
            cache_ttl_s=0.0,
            fallback="That action did not finish. I did not retry it.",
        )

    @staticmethod
    def _cache_key(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        safe_kwargs = {key: value for key, value in kwargs.items() if key != "context"}
        payload = json.dumps(
            {"name": name, "args": args[1:], "kwargs": safe_kwargs},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def wrap(
        self,
        *,
        name: str,
        read_only: bool,
        requires_approval: bool,
        handler: Callable[..., Awaitable[str]],
    ) -> Callable[..., Awaitable[str]]:
        policy = self.policy(read_only=read_only, requires_approval=requires_approval)

        @functools.wraps(handler)
        async def managed(*args: Any, **kwargs: Any) -> str:
            context = args[0] if args else kwargs.get("context")
            key = self._cache_key(name, args, kwargs)
            cached = self._cache.get(key)
            now = time.monotonic()
            if cached and cached.expires_at > now:
                _log.info("TOOL_LATENCY name=%s cache=hit elapsed_ms=0", name)
                if self._on_timing is not None:
                    self._on_timing(name, 0.0, True)
                return cached.value

            async def execute() -> str:
                last_error: Exception | None = None
                for attempt in range(policy.retries + 1):
                    try:
                        return await asyncio.wait_for(handler(*args, **kwargs), policy.timeout_s)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - bounded retry policy
                        last_error = exc
                        if attempt < policy.retries:
                            await asyncio.sleep(0.08 * (attempt + 1))
                _log.warning("tool %s failed: %s", name, type(last_error).__name__)
                return policy.fallback

            started = time.perf_counter()
            filler = getattr(context, "with_filler", None)
            if callable(filler):
                async with filler(
                    "Checking that now.",
                    delay=0.0,
                    interval=6.0,
                    max_steps=2,
                ):
                    value = await execute()
            else:
                value = await execute()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            _log.info("TOOL_LATENCY name=%s cache=miss elapsed_ms=%.1f", name, elapsed_ms)
            if self._on_timing is not None:
                self._on_timing(name, elapsed_ms, False)

            if policy.cache_ttl_s > 0 and value != policy.fallback:
                self._cache[key] = _CacheEntry(now + policy.cache_ttl_s, value)
            return value

        return managed
