"""Consolidate Wave 8.4 embedded arm evidence without making a production claim."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _get(payload: dict[str, Any], *path: str) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def main() -> int:
    evidence_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("worker/bench/evidence/wave84")
    rows: list[dict[str, Any]] = []
    for path in sorted(evidence_dir.glob("*-groq.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        external = _get(payload, "analysis", "classification") or {}
        worker_stages = _get(payload, "worker_profile", "stages") or {}
        rows.append(
            {
                "arm": path.stem,
                "captured_at": payload.get("captured_at"),
                "model": payload.get("llm_model"),
                "samples": external.get("samples"),
                "external_v2v_p50_ms": external.get("v2v_p50_ms"),
                "external_v2v_p95_ms": external.get("v2v_p95_ms"),
                "barge_in_p95_ms": _get(payload, "interruption", "barge_in_p95_ms"),
                "cut_off_rate": payload.get("cut_off_rate"),
                "worker_stages": worker_stages,
            }
        )
    portal_rows = [row for row in rows if "phonecall" not in row["arm"]]
    eligible = [row for row in portal_rows if row["external_v2v_p50_ms"] is not None]
    selected = min(eligible, key=lambda row: row["external_v2v_p50_ms"])["arm"] if eligible else None
    output = {
        "method": "embedded_livekit_audio_matrix",
        "production_tier_claim": None,
        "note": (
            "Arm selection evidence only. A tier claim requires worker_info from the verified "
            "production worker; the 8kHz phone arm simulates narrowband and is not carrier v2v."
        ),
        "selected_portal_arm": selected,
        "arms": rows,
    }
    target = evidence_dir / "matrix-summary.json"
    target.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
