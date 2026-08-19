"""Smoke a candidate Groq fallback model against Samuel's calendar tool contract.

This does not write a calendar event. It only requires the model to emit the
proposal tool call that the worker would send to rainmaker-api after validation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--base-url", default="https://api.groq.com/openai/v1")
    return parser.parse_args()


def main() -> int:
    args = _args()
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / "worker" / ".env")
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        print("GROQ_API_KEY is not configured", file=sys.stderr)
        return 2

    tool = {
        "type": "function",
        "function": {
            "name": "propose_calendar_change",
            "description": (
                "Propose one calendar create, update, or cancel. This never commits."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "update", "cancel"],
                    },
                    "summary": {"type": ["string", "null"]},
                    "start": {"type": ["string", "null"]},
                    "end": {"type": ["string", "null"]},
                    "duration_minutes": {"type": ["integer", "null"]},
                    "event_id": {"type": ["string", "null"]},
                    "event_query": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "location": {"type": ["string", "null"]},
                    "all_day": {"type": ["boolean", "null"]},
                    "timezone": {"type": ["string", "null"]},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    }
    body = {
        "model": args.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Samuel. Calendar writes must call the supplied proposal "
                    "tool and wait for a later confirmation."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Add a dentist appointment tomorrow at 4 PM Pacific for 30 minutes."
                ),
            },
        ],
        "tools": [tool],
        "tool_choice": "required",
        "temperature": 0,
        "max_completion_tokens": 512,
    }
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{args.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=20,
        )
    except httpx.HTTPError as exc:
        print(f"fallback request did not reach a healthy provider: {exc}", file=sys.stderr)
        return 1
    if response.status_code != 200:
        print(
            f"fallback request failed: HTTP {response.status_code} {response.text[:300]}",
            file=sys.stderr,
        )
        return 1
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    message = (response.json().get("choices") or [{}])[0].get("message") or {}
    calls = message.get("tool_calls") or []
    if len(calls) != 1:
        print(f"expected one tool call, received {len(calls)}", file=sys.stderr)
        return 1
    call = calls[0].get("function") or {}
    if call.get("name") != "propose_calendar_change":
        print(f"unexpected tool: {call.get('name')!r}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(call.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        print(f"tool arguments are not JSON: {exc}", file=sys.stderr)
        return 1
    if payload.get("action") != "create":
        print(f"wrong calendar action: {payload.get('action')!r}", file=sys.stderr)
        return 1
    if not payload.get("summary") or not payload.get("start"):
        print(f"missing required proposal meaning: {payload}", file=sys.stderr)
        return 1
    if not payload.get("end") and not payload.get("duration_minutes"):
        print(f"proposal omitted both end and duration: {payload}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "model": args.model,
                "tool": call["name"],
                "action": payload["action"],
                "has_end_or_duration": True,
                "elapsed_ms": round(elapsed_ms, 1),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
