# S.A.M. worker (Samuel's runtime)

Python LiveKit agent worker: STT → Hermes brain → ElevenLabs TTS, with the Rainmaker command
surface and the server half of the TierController.

## Run

```bash
# Offline simulated turn loop — no installs, no keys:
python -m sam_worker --mock --turns 8

# Tests (stdlib only):
python -m pytest

# Real run (Phase 5 — needs .env): 
python -m sam_worker
uvicorn server.token_server:app --port 8788
```

## Layout

| Module | Role | Status |
|---|---|---|
| `sam_worker/agent.py` | real LiveKit entrypoint | stub (Phase 5) |
| `sam_worker/brain.py` | Hermes OpenAI-compatible client | `MockBrain` works; `HermesBrain` stub |
| `sam_worker/stt.py` / `tts.py` | Deepgram / ElevenLabs stages | stub (Phase 5) |
| `sam_worker/personas.py` | Samuel + Schedule/Design/Sales | done |
| `sam_worker/tier.py` | per-tier model + memory (server half) | done |
| `sam_worker/tools/rainmaker.py` | rm_api command surface, read-only first | schema + mock |
| `sam_worker/mock_loop.py` | offline turn loop | done |
| `server/token_server.py` | LiveKit token minting | health stub |

The brain is **Hermes** (internal "Charles"); never surface that name to customers — they only
meet **Samuel**.
