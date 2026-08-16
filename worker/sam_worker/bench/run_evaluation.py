"""CLI for producing the canonical Wave 8 intelligence scorecard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluation import evaluate_observations, load_observations


def main() -> int:
    parser = argparse.ArgumentParser(description="Score Samuel Wave 8 observations")
    parser.add_argument("observations", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--arm", default="samuel")
    parser.add_argument("--v2v-ms", default="", help="comma-separated full-pipeline samples")
    parser.add_argument("--barge-in-f1", type=float, default=0.0)
    parser.add_argument("--interruption-accuracy", type=float, default=0.0)
    parser.add_argument("--learning-efficiency", type=float)
    args = parser.parse_args()

    samples = [float(value) for value in args.v2v_ms.split(",") if value.strip()]
    report = evaluate_observations(
        load_observations(args.observations),
        v2v_ms=samples,
        barge_in_f1=args.barge_in_f1,
        interruption_accuracy=args.interruption_accuracy,
        learning_efficiency=args.learning_efficiency,
        arm=args.arm,
    )
    payload = json.dumps(report.summary(), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if not report.failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
