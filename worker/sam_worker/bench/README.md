# Samuel benchmark harness

Implements the scorecard from `rainMaker/studios/research/sam-benchmark-methodology.md`.

**Status: runnable for Samuel.** The external LiveKit audio driver publishes deterministic,
synthetic speech and measures returned audio at the room boundary. The grounded evaluation consumes
versioned observations and the existing two-arena scorecard. ChatGPT Voice remains disabled.

## Files

- `scorecard.py` — metric containers + composite scoring (two arenas), pure + testable now.
- `fixtures.py` — versioned grounded-task / interruption / general-Q&A suites (ground-truth backed).
- `bench_config.json` — the arms (`samuel`, `samuel-groq`, `chatgpt-voice`, `samuel-s2s`), KPI gates,
  sample sizes, and composite weights.
- `livekit_audio.py` / `run_audio_bench.py` — full transport/STT/EOU/LLM/TTS audio driver.
- `evaluation.py` / `run_evaluation.py` — deterministic grounded/intelligence scorer.
- `worker/bench/audio/manifest.json` — 10 short, 10 long, and controlled barge-in fixtures.

## Two arenas (why)

- **General arena** (latency, barge-in, naturalness, recovery/charm): level playing field. A
  speech-to-speech agent like ChatGPT voice is expected to win raw latency — an accepted ADR-2 trade.
- **Grounded arena** (task success, anti-hallucination, tool accuracy, refusal): Samuel's reason to
  exist. ChatGPT voice *cannot play* (no access to your platform). Reported as Samuel's absolute
  capability, not a default-win head-to-head.

## Full-audio run

From the repository root on Windows:

1. `.\scripts\generate-wave8-audio.ps1`
2. From `worker`, run:
   `python -m sam_worker.bench.run_audio_bench bench/audio/manifest.json --turn-mode cloud --output bench/results/cloud.json`

The driver requires `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`. Generated WAV files
and raw result files are gitignored. Repeat after selecting each deployed `SAM_TURN_MODE`; never
label a mode from CLI differently from the worker configuration actually under test.

The first Wave 8 matrix is tracked in
`worker/bench/evidence/wave8-2026-08-15.json`. STT was the fastest mode with no detected cutoffs,
but it still missed Minimum Enterprise (1503 ms p50 / 1853 ms p95). Adaptive interruption remains
the safe default: VAD interruption produced a 213 ms best case but falsely stopped on both
backchannel decoys and was unstable on repeat.

For intelligence scoring:

`python -m sam_worker.bench.run_evaluation observations.json --output scorecard.json`

## Test

`python -m pytest tests/test_bench_scorecard.py tests/test_livekit_audio_bench.py
tests/test_skillbuilder_runtime.py` covers score math, audio transport primitives, KPI/consent, and
the intelligence report.
