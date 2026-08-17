"""One-shot SAM-078 token-budget breakdown. No deploy, no LLM call.

Usage (from worker/):
  python -m sam_worker.bench.token_budget
  python -m sam_worker.bench.token_budget --output bench/evidence/wave82-token-budget.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ..prompt_budget import (
    GROQ_8B_TPM,
    TARGET_PROMPT_TOKENS,
    all_rainmaker_specs,
    breakdown,
    samuel_instructions,
    specs_named,
)
from ..tools.select import VOICE_TOOLS, select_tools_for_utterance

# Representative unrouted turns from the Wave 8 fixtures.
_UNROUTED = (
    "How much does Rainmaker cost per month?",
    "Tell me a short story about the market.",
    "Should I buy NVDA right now?",
)

# Two prior turns of typical spoken length (~40 tokens each side).
_SHORT_HISTORY = (
    "user: hey sam what's going on",
    "assistant: Not much — I'm here. What do you want to look at?",
    "user: How much does Rainmaker cost per month?",
)


def _report() -> dict:
    specs = all_rainmaker_specs()
    system = samuel_instructions()
    full = breakdown(system=system, specs=specs, history=_SHORT_HISTORY)
    voice = breakdown(
        system=system,
        specs=specs_named(VOICE_TOOLS),
        history=_SHORT_HISTORY,
    )
    typical_rows = []
    for utterance in _UNROUTED:
        names = select_tools_for_utterance(utterance)
        hist = _SHORT_HISTORY[:-1] + (f"user: {utterance}",)
        row = breakdown(system=system, specs=specs_named(names), history=hist)
        typical_rows.append(
            {
                "utterance": utterance,
                "tools": names,
                **row.to_dict(),
            }
        )
    typical_total = (
        max(r["total_tokens"] for r in typical_rows) if typical_rows else full.total_tokens
    )
    return {
        "wave": "8.2",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": "estimate_tokens_chars_div_4",
        "target_prompt_tokens": TARGET_PROMPT_TOKENS,
        "groq_8b_tpm": GROQ_8B_TPM,
        "full_14_tools": full.to_dict(),
        "voice_9_tools": voice.to_dict(),
        "typical_unrouted": typical_rows,
        "conclusion": {
            "full_dump_dominant": full.dominant == "tool_schema",
            "full_dump_share": (
                round(full.tool_schema_tokens / full.total_tokens, 3)
                if full.total_tokens
                else 0
            ),
            "typical_max_tokens": typical_total,
            "typical_under_target": typical_total <= TARGET_PROMPT_TOKENS,
            "typical_turns_per_minute_at_6k": (
                round(GROQ_8B_TPM / typical_total, 2) if typical_total else 0
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Samuel prompt token budget (SAM-078)")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    payload = _report()
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
