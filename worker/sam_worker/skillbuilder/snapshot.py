"""SAM-058: live HERO snapshot JSON (ADR-9: rm_api fetches this over the network)."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from .character_sheet import build_character_sheet
from .runtime import SkillBuilderRuntime


def live_snapshot(runtime: SkillBuilderRuntime | None = None, kpis: dict | None = None) -> dict:
    merged = dict(kpis or {})
    if runtime is not None:
        v2v_values = runtime.metric_values("samuel_live_session", "v2v_ms")
        if v2v_values:
            merged.setdefault("v2v_p50_ms", statistics.median(v2v_values))
        merged.setdefault("autonomy_mode", "advisory")
    return build_character_sheet(kpis=merged)


def write_snapshot(path: Path, snapshot: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
