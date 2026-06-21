# S.A.M. — System Agentic Model (Samuel)

**Samuel ("Sam")** is the flagship customer-facing voice agent for the Rainmaker platform — and
the Rainmaker trading agent. **Hermes** (internal codename "Charles") is the invisible
orchestrator/brain; customers only ever meet Samuel.

This repo is the dedicated, enterprise-class voice product. It is intentionally **separate** from
the Rainmaker monorepo and the old Charles voice PWA (which this replaces once live).

> Design source of truth lives in the Rainmaker repo:
> - `studios/research/sam-architecture.md` — realtime architecture & adaptive tiering research
> - `studios/research/sam-adr.md` — Architecture Decision Record (locked decisions)
> - `studios/research/sam-tiercontroller-spec.md` — the adaptive quality engine spec
> - `.cursor/plans/charles_voice_flagship_33db4451.plan.md` — the build plan

## Prime directive

**Speech is never sacrificed.** The north-star KPI is voice-to-voice latency
**≤ 800ms p50 / ≤ 1500ms p95**. Every adaptive-quality decision protects natural speech cadence
above visuals, memory, brain model, and even voice richness.

## Architecture (cascaded streaming pipeline on LiveKit)

```
client/  (React + Vite + TS + Rive)        worker/  (Python + LiveKit Agents)
  - Samuel avatar (tiered visual)            - turn-taking (model-based endpointing)
  - LatencyHUD (proves the KPI)              - STT: Deepgram Nova-3        (stub)
  - TierController (fps + bandwidth)         - brain: Hermes (OpenAI-compat)(stub)
  - LiveKit room client        <--WebRTC-->  - TTS: ElevenLabs Flash v2.5  (stub)
  - mock transport (no keys)                 - tools: Rainmaker rm_api     (stub)
                                             - token server (mint LiveKit JWT)
```

## Status: Phase 4 scaffold (stubs)

This is a **structure + stubs** scaffold. It **boots locally with mock providers** and needs no
real vendor keys. Real LiveKit / Deepgram / ElevenLabs / Hermes wiring lands in **Phase 5 (Speed
POC)**, gated by the <800ms KPI.

- The **client** runs against a built-in `MockTransport` that simulates a turn loop so the
  TierController + LatencyHUD are reviewable end-to-end without a backend.
- The **worker** has a `--mock` loop (stdlib only) that simulates turns and prints per-stage
  timings; the real LiveKit agent entrypoint is stubbed with clear TODOs.

## Quick start

### Client
```bash
cd client
npm install
npm run dev        # http://localhost:5173  (mock transport, no keys needed)
npm run test       # TierController unit tests (vitest)
npm run build      # typecheck + production build
```

### Worker
```bash
cd worker
python -m sam_worker --mock     # simulated turn loop, no external services
# real run (Phase 5, needs .env): python -m sam_worker
python -m pytest                # tier-map + persona tests
```

Copy `.env.example` → `.env` in each package before a real run. **Never commit real secrets.**

## Repo layout

| Path | What |
|---|---|
| `client/src/tier/` | TierController FSM, presets, fps/net samplers (the adaptive engine) |
| `client/src/components/` | Samuel avatar, latency HUD, mic button, tier badge |
| `client/src/lib/` | LiveKit room client (stub) + mock transport |
| `worker/sam_worker/` | agent entrypoint, brain/stt/tts/personas/tier, mock loop |
| `worker/sam_worker/tools/` | Rainmaker command surface client (read-only first) |
| `worker/server/` | LiveKit token server (FastAPI) |

## Naming canon

- **Samuel / Sam** — the only customer-facing agent. Never expose "Hermes"/"Charles" to users.
- **Hermes** — the brain/orchestrator (`charles_bridge`/`ask_charles` in rm_api is Hermes).
- Sub-agent demo personas: **Schedule, Design, Sales** (trading = Samuel himself).
- Live trading (research/place/sell on a shadow account) is a **later branch**.
