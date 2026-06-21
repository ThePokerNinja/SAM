"""CLI entry: `python -m sam_worker [--mock] [--turns N]`."""

from __future__ import annotations

import argparse
import asyncio
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sam_worker", description="S.A.M. agent worker")
    parser.add_argument("--mock", action="store_true", help="run the offline simulated turn loop")
    parser.add_argument(
        "--bench",
        action="store_true",
        help="Phase 5 latency harness against real brains + ElevenLabs (needs worker/.env)",
    )
    parser.add_argument(
        "--mode",
        choices=["ab", "rest", "ws"],
        default="ab",
        help="bench mode: ab=rest+ws (default), rest=sentence+REST TTS, ws=input-streaming TTS",
    )
    parser.add_argument("--turns", type=int, default=6, help="number of turns (mock/bench)")
    args = parser.parse_args(argv)

    if args.mock:
        from .mock_loop import run_mock

        asyncio.run(run_mock(turns=args.turns))
        return 0

    # Load worker/.env for any real run (bench or agent).
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:  # python-dotenv optional in --mock-only environments
        pass

    if args.bench:
        from .harness import run_bench

        return asyncio.run(run_bench(turns=args.turns if args.turns != 6 else 10, mode=args.mode))

    print(
        "Real LiveKit agent is run via its own CLI:\n"
        "  python -m sam_worker.agent console   # local mic/speaker quick test\n"
        "  python -m sam_worker.agent dev       # register with LiveKit Cloud + Agents Playground\n"
        "Offline: python -m sam_worker --mock  |  Latency bench: python -m sam_worker --bench",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
