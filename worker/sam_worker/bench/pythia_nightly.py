"""Nightly Pythia calibration: Brier score -> SkillCandidate if over threshold.

Scheduled by ``sam_worker.nightly`` inside the worker, since sam-agent owns the
disk holding the ledger. Also runnable by hand against the same sqlite:

  python -m sam_worker.bench.pythia_nightly
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from sam_worker.pythia import ForecastLedger
from sam_worker.skillbuilder.advisory import run_advisory
from sam_worker.skillbuilder.gap import candidate_from_pythia_brier
from sam_worker.skillbuilder.runtime import SkillBuilderRuntime

Notifier = Callable[[str, str], Any]


def run(
    db_path: Path,
    subject: str = "next_turn_latency_over_800",
    *,
    notify: Notifier | None = None,
) -> dict:
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
    # The ledger's sample floor and Brier threshold are the filter that earns an SMS;
    # calibration candidates are advisory by design and rarely clear adoption gates.
    # Ask once per candidate so a standing miscalibration cannot text nightly.
    already_asked = runtime.approval_count(candidate.candidate_id) > 0
    run_advisory(runtime, candidate, reason=candidate.problem_detected)
    notified = False
    if notify is not None and not already_asked:
        try:
            result = notify(candidate.candidate_id, candidate.problem_detected) or {}
            notified = bool(result.get("ok"))
        except Exception:  # noqa: BLE001 - a failed SMS must not lose the candidate
            notified = False
    return {
        "ok": True,
        "emitted": True,
        "candidateId": candidate.candidate_id,
        "approvedForAdoption": candidate.gates.approved_for_adoption,
        "notified": notified,
        "samples": raw["sample_count"],
        "brier": raw["brier"],
    }


def main() -> None:
    from sam_worker.memory.episodic import memory_db_path

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="")
    parser.add_argument("--subject", default="next_turn_latency_over_800")
    args = parser.parse_args()
    db = Path(args.db) if args.db else memory_db_path()
    print(json.dumps(run(db, args.subject)))


if __name__ == "__main__":
    main()
