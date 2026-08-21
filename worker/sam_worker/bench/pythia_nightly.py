"""Nightly Pythia calibration: Brier score -> SkillCandidate if over threshold.

Run from the SAM worker image or a cron hitting the memory sqlite:

  python -m sam_worker.bench.pythia_nightly --db /var/data/episodes.db
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sam_worker.pythia import ForecastLedger
from sam_worker.skillbuilder.advisory import run_advisory
from sam_worker.skillbuilder.gap import candidate_from_pythia_brier
from sam_worker.skillbuilder.runtime import SkillBuilderRuntime


def run(db_path: Path, subject: str = "next_turn_latency_over_800") -> dict:
    ledger = ForecastLedger(db_path)
    runtime = SkillBuilderRuntime(db_path)
    raw = ledger.calibration_candidate(subject=subject)
    if raw is None:
        count, score = ledger.calibration(subject)
        return {"ok": True, "emitted": False, "samples": count, "brier": score}
    candidate = candidate_from_pythia_brier(
        subject,
        sample_count=int(raw["sample_count"]),
        brier=float(raw["brier"]),
    )
    run_advisory(runtime, candidate, reason=candidate.problem_detected)
    return {
        "ok": True,
        "emitted": True,
        "candidateId": candidate.candidate_id,
        "approvedForAdoption": candidate.gates.approved_for_adoption,
        "samples": raw["sample_count"],
        "brier": raw["brier"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/var/data/episodes.db")
    parser.add_argument("--subject", default="next_turn_latency_over_800")
    args = parser.parse_args()
    print(json.dumps(run(Path(args.db), args.subject)))


if __name__ == "__main__":
    main()
