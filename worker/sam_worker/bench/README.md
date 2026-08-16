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

Canonical evidence: `worker/bench/evidence/wave8-2026-08-15.json` (Wave 8) and
`worker/bench/evidence/wave81-2026-08-16.json` (Wave 8.1).

## Barge-in t=0 (do not regress)

The 1081ms Wave 8 production barge-in number was mostly harness error. `measure_barge_in` must:

1. **t=0 = first voiced interrupt frame**, not `time.perf_counter()` before `publish_fixture`.
   `publish_fixture` already returns `PublishTiming.first_voice_at`.
2. **Subtract `AUDIO_PAUSED_LAG_S` (100ms).** `audio_paused` is our derived event: it fires on
   the 6th silent 20ms frame, so elapsed time from the first silent frame is five intervals.
3. **Publish the interrupt with `reset=False`.** Resetting mid-turn clears `_speaking` and the
   monitor cannot emit `audio_paused` until it re-detects speech.

A known-offset unit test in `tests/test_livekit_audio_bench.py` locks this. If a barge-in number
jumps by ~400–1000ms after a harness edit, distrust the clock before retuning interruption.

## EOU 0.30 → 0.78

That step is LiveKit **dynamic** endpointing interpolating toward `SAM_ENDPOINTING_MAX`, not
prompt growth. Production max of 1.2s produced the 777ms floor. The measured default is
**STT + 0.25 / 0.6**. `Settings.from_env()` caps max at 0.6 so a stale Render env cannot
bring 1.2 back.

For intelligence scoring:

`python -m sam_worker.bench.run_evaluation observations.json --output scorecard.json`

## Test

`python -m pytest tests/test_bench_scorecard.py tests/test_livekit_audio_bench.py
tests/test_skillbuilder_runtime.py` covers score math, audio transport primitives, KPI/consent, and
the intelligence report.
