"""Latency-profile analyzer (PDF Phase 1 / ADR-24).

Ingests the per-turn JSONL written by ``sam_worker.latency.write_profile`` (when
``SAM_LATENCY_LOG=1``), computes per-stage p50/p90/p95, and classifies the run against the tiered
targets (Minimum Enterprise / Premium ship gate / Industry-Leading) from ``bench_config.json``.

Pure / offline: no live pipeline needed. Reuses ``scorecard.percentile`` for the percentile
convention so the bench is internally consistent.
"""

from __future__ import annotations

import json
from pathlib import Path

from .scorecard import percentile

# Stages we summarize when present in the JSONL rows.
_STAGES = (
    "eou_ms",
    "transcription_delay_ms",
    "turn_callback_ms",
    "stt_ms",
    "llm_ttft_ms",
    "llm_duration_ms",
    "tts_ttfb_ms",
    "tts_duration_ms",
    "tts_audio_ms",
    "playback_start_ms",
    "route_ms",
    "context_ms",
    "tool_ms",
    "barge_in_ms",
    "v2v_ms",
)

# Fallback tiers if a config is not supplied (kept in sync with bench_config.json).
DEFAULT_TIERED_TARGETS = {
    "minimum_enterprise": {"v2v_p50_ms": 1000, "v2v_p95_ms": 1500, "barge_in_ms": 400},
    "premium": {"v2v_p50_ms": 800, "v2v_p95_ms": 1200, "barge_in_ms": 250},
    "industry_leading": {"v2v_p50_ms": 600, "v2v_p95_ms": 1000, "barge_in_ms": 150},
}

# Best -> worst, so we can pick the highest tier a run satisfies.
_TIER_ORDER = ("industry_leading", "premium", "minimum_enterprise")


def load_tiered_targets(config_path: Path | None = None) -> dict:
    """Load ``tiered_targets`` from a bench config, falling back to the defaults."""
    if config_path is None:
        config_path = Path(__file__).with_name("bench_config.json")
    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        return cfg.get("tiered_targets", DEFAULT_TIERED_TARGETS)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_TIERED_TARGETS


def _collect(rows: list[dict], key: str) -> list[float]:
    """Numeric, non-null values for a stage across rows."""
    out: list[float] = []
    for r in rows:
        v = r.get(key)
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def stage_percentiles(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Per-stage p50/p90/p95 + sample count for every populated stage."""
    summary: dict[str, dict[str, float]] = {}
    for stage in _STAGES:
        vals = _collect(rows, stage)
        if not vals:
            continue
        summary[stage] = {
            "p50": round(percentile(vals, 50), 1),
            "p90": round(percentile(vals, 90), 1),
            "p95": round(percentile(vals, 95), 1),
            "n": float(len(vals)),
        }
    return summary


def _meets(tier: dict, v2v_p50: float | None, v2v_p95: float | None, barge_p95: float | None) -> bool:
    """A tier is met only when every dimension that has data passes; missing data does not pass."""
    if v2v_p50 is None or v2v_p95 is None:
        return False
    if v2v_p50 >= tier["v2v_p50_ms"] or v2v_p95 >= tier["v2v_p95_ms"]:
        return False
    # Every canonical tier includes a barge-in target. Missing evidence cannot pass.
    return barge_p95 is not None and barge_p95 < tier["barge_in_ms"]


def classify_tier(
    rows: list[dict],
    targets: dict | None = None,
) -> dict:
    """Classify a set of turn profiles against the tiered targets.

    Returns the highest tier satisfied (or ``none``) plus the headline numbers and per-tier pass map.
    """
    targets = targets or load_tiered_targets()
    v2v = _collect(rows, "v2v_ms")
    barge = _collect(rows, "barge_in_ms")
    v2v_p50 = round(percentile(v2v, 50), 1) if v2v else None
    v2v_p95 = round(percentile(v2v, 95), 1) if v2v else None
    barge_p95 = round(percentile(barge, 95), 1) if barge else None

    per_tier = {
        name: _meets(targets[name], v2v_p50, v2v_p95, barge_p95)
        for name in targets
    }
    tier = "none"
    for name in _TIER_ORDER:
        if per_tier.get(name):
            tier = name
            break
    return {
        "tier": tier,
        "v2v_p50_ms": v2v_p50,
        "v2v_p95_ms": v2v_p95,
        "barge_in_p95_ms": barge_p95,
        "samples": len(v2v),
        "per_tier": per_tier,
    }


def analyze(rows: list[dict], targets: dict | None = None) -> dict:
    """Full summary: per-stage percentiles + tier classification."""
    modes = sorted({str(row.get("turn_mode")) for row in rows if row.get("turn_mode")})
    return {
        "stages": stage_percentiles(rows),
        "classification": classify_tier(rows, targets),
        "turns": len(rows),
        "by_turn_mode": {
            mode: classify_tier(
                [row for row in rows if str(row.get("turn_mode")) == mode], targets
            )
            for mode in modes
        },
    }


def analyze_eou_drift(rows: list[dict]) -> dict:
    """Correlate EOU with turn index, prompt size, and transcript length.

    The production stall we keep seeing is EOU stepping from ~300ms to ~780ms
    mid-session. This report says whether that step tracks turn order (context
    growth) or utterance length.
    """
    indexed = [
        row
        for row in rows
        if isinstance(row.get("eou_ms"), (int, float))
        and isinstance(row.get("turn_index"), int)
    ]
    by_index: dict[int, list[float]] = {}
    for row in indexed:
        by_index.setdefault(int(row["turn_index"]), []).append(float(row["eou_ms"]))
    early = [float(row["eou_ms"]) for row in indexed if int(row["turn_index"]) <= 3]
    late = [float(row["eou_ms"]) for row in indexed if int(row["turn_index"]) >= 4]
    token_pairs = [
        (float(row["prompt_tokens"]), float(row["eou_ms"]))
        for row in indexed
        if isinstance(row.get("prompt_tokens"), (int, float))
    ]
    char_pairs = [
        (float(row["transcript_chars"]), float(row["eou_ms"]))
        for row in indexed
        if isinstance(row.get("transcript_chars"), (int, float))
    ]

    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None

    return {
        "n": len(indexed),
        "early_eou_ms": _mean(early),
        "late_eou_ms": _mean(late),
        "step_ms": (
            round(_mean(late) - _mean(early), 1)
            if early and late and _mean(late) is not None and _mean(early) is not None
            else None
        ),
        "by_turn_index": {
            str(index): round(sum(values) / len(values), 1)
            for index, values in sorted(by_index.items())
        },
        "prompt_token_pairs": token_pairs,
        "transcript_char_pairs": char_pairs,
        "tracks_turn_index": bool(
            early and late and _mean(late) is not None and _mean(early) is not None
            and (_mean(late) or 0) - (_mean(early) or 0) >= 200
        ),
    }


def analyze_file(path: str | Path, targets: dict | None = None) -> dict:
    """Convenience: read a JSONL profile file and analyze it."""
    from ..latency import read_profiles

    rows = read_profiles(Path(path))
    return analyze(rows, targets)
