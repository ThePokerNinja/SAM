"""SAM-058: live HERO snapshot JSON (ADR-9: rm_api fetches this over the network)."""

from __future__ import annotations

import json
from pathlib import Path

from .character_sheet import build_character_sheet
from .runtime import SkillBuilderRuntime


def live_snapshot(runtime: SkillBuilderRuntime | None = None, kpis: dict | None = None) -> dict:
    merged = dict(kpis or {})
    if runtime is not None:
        latest = runtime.latest_kpis("trading")
        if "v2v_p50_ms" in latest:
            merged.setdefault("v2v_p50_ms", latest["v2v_p50_ms"].metric_value)
        merged.setdefault("autonomy_mode", "advisory")
    return build_character_sheet(kpis=merged)


def write_snapshot(path: Path, snapshot: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
