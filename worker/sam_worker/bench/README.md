# Samuel benchmark harness (scaffold)

Implements the scorecard from `rainMaker/studios/research/sam-benchmark-methodology.md`.

**Status: scaffold.** The scorecard math (`scorecard.py`) and fixtures (`fixtures.py`) are real and
unit-tested. The live arms (driving Samuel / ChatGPT voice end-to-end) are **not** run yet — wire
them after Wave 1 (Hermes brain + read-only tools) makes the grounded arena real.

## Files

- `scorecard.py` — metric containers + composite scoring (two arenas), pure + testable now.
- `fixtures.py` — versioned grounded-task / interruption / general-Q&A suites (ground-truth backed).
- `bench_config.json` — the arms (`samuel`, `samuel-groq`, `chatgpt-voice`, `samuel-s2s`), KPI gates,
  sample sizes, and composite weights. All arms `enabled: false` until wired.

## Two arenas (why)

- **General arena** (latency, barge-in, naturalness, recovery/charm): level playing field. A
  speech-to-speech agent like ChatGPT voice is expected to win raw latency — an accepted ADR-2 trade.
- **Grounded arena** (task success, anti-hallucination, tool accuracy, refusal): Samuel's reason to
  exist. ChatGPT voice *cannot play* (no access to your platform). Reported as Samuel's absolute
  capability, not a default-win head-to-head.

## When this becomes runnable

1. Land Wave 1 (`HermesBrain` + `HttpRainmakerClient` + registered read-only tools).
2. Fill `fixtures.py` ground truth from the prod-session table + real rm_api responses.
3. Add live drivers (LiveKit arm; OpenAI realtime arm respecting ToS) behind the `enabled` flags.
4. Run baseline, tune EOU to the latency gate, then publish the first two-arena scorecard with raw
   JSONL runs.

## Test

`python -m pytest worker/tests/test_bench_scorecard.py` covers the composite math and the ADR-8
latency gate.
