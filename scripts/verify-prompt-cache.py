"""Compare Groq prompt-cache usage for Samuel's stable full-tool prefix."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
sys.path.insert(0, str(WORKER))

from sam_worker.prompt_budget import (
    all_rainmaker_specs,
    stable_samuel_instructions,
    tool_openai_schema,
)


def _cached_tokens(usage: dict) -> int:
    details = usage.get("prompt_tokens_details") or {}
    return int(
        details.get("cached_tokens")
        or usage.get("prompt_cached_tokens")
        or usage.get("cached_tokens")
        or 0
    )


def main() -> int:
    load_dotenv(WORKER / ".env")
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        print("GROQ_API_KEY is not configured", file=sys.stderr)
        return 2
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
    tools = [tool_openai_schema(spec) for spec in all_rainmaker_specs()]
    base = {
        "model": model,
        "temperature": 0,
        "max_completion_tokens": 64,
        "tool_choice": "none",
        "tools": tools,
    }
    prompts = (
        "Answer with the single word ready.",
        "Answer with the single word ready.",
    )
    results: list[dict] = []
    with httpx.Client(timeout=20) as client:
        for prompt in prompts:
            response = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    **base,
                    "messages": [
                        {"role": "system", "content": stable_samuel_instructions()},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            if response.status_code != 200:
                print(
                    f"cache probe failed: HTTP {response.status_code} {response.text[:300]}",
                    file=sys.stderr,
                )
                return 1
            usage = response.json().get("usage") or {}
            results.append(
                {
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "cached_tokens": _cached_tokens(usage),
                    "usage_keys": sorted(usage),
                    "prompt_time_s": usage.get("prompt_time"),
                    "remaining_tokens": response.headers.get(
                        "x-ratelimit-remaining-tokens"
                    ),
                    "reset_tokens": response.headers.get("x-ratelimit-reset-tokens"),
                }
            )
            time.sleep(0.25)
    output = {
        "ok": True,
        "model": model,
        "tool_count": len(tools),
        "first": results[0],
        "second": results[1],
        "cache_hit": results[1]["cached_tokens"] > 0,
    }
    print(json.dumps(output, sort_keys=True))
    # Cache population is best-effort. A clean probe is success even when Groq
    # reports a miss; callers use cache_hit to decide whether to enable the arm.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
