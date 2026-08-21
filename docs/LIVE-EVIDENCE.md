# Live agent-OS evidence

## 2026-08-21 SAM-043/044 artifact brief

- Runtime SHA: `0b95e2c8ce4f` (`sam-agent`, Render). Dashboard now has
  `SAM_MEMORY_ENABLED=1` and `SAM_CACHE_DIR=/var/data` (they were in
  `render.yaml` but not on the service — Wave 8.1 env-drift).
- Write room `sam-wave8-502fbb992cb1` and recall room `sam-wave8-7b6d6beb92b5`
  both published `prior_artifact_brief` (non-empty). Owner-token production
  audio, no phone call. 35s settle after write so the per-job process can
  finish session-close persist.
- Canonical evidence: `worker/bench/evidence/agent-os-artifact-write-live-0b95e2c.json`,
  `worker/bench/evidence/agent-os-artifact-recall-live-0b95e2c.json`.
  Re-run: `.\scripts\run-artifact-proof.ps1`.

## 2026-08-21 production close

- Runtime SHA: `2f80e882b843` (`sam-agent`, Render).
- SAM-039: production audio activated Moderator, Appointment, and SkillBuilder packs.
- SAM-040/041: owner-role production sessions wrote and recalled `ultramarine`
  across separate LiveKit rooms on `9af52040eb31`.
- SAM-043/044: closed later the same day — see section above. Earlier runs on
  `2f80e88` recalled Lighthouse from canonical owner memory without
  `prior_artifact_brief` because memory was off.
- SAM-038, SAM-042/045/046, and Moderator two-party acceptance remain open
  because no physical or two-participant call was authorized.
- Premium latency remains open: agent-OS functional run measured 1047.8 ms p50;
  the full production run measured 1199.7 ms p50 and 1172 ms barge-in.

Canonical evidence:

- `worker/bench/evidence/agent-os-live-a8a203d.json`
- `worker/bench/evidence/agent-os-memory-write-live-9af5204-rerun.json`
- `worker/bench/evidence/agent-os-memory-recall-live-9af5204-rerun.json`
- `worker/bench/evidence/agent-os-artifact-write-live-2f80e88.json`
- `worker/bench/evidence/agent-os-artifact-recall-live-2f80e88.json`
- `worker/bench/evidence/wave6-runtime-live-a8a203d.json`

## Five-lens assessment

- **Scalability:** SQLite WAL and bounded reads are suitable for the single
  persistent worker. Multi-replica tenancy remains unproven.
- **Performance:** context, memory, prediction, and artifact writes stay
  asynchronous, but measured Premium voice latency still fails.
- **Memory:** retrieval is token-bounded and summary checkpoints replace in
  place. Artifact-source live proof is closed (`prior_artifact_brief` count > 0).
  Retention/deletion policy remains open. Per-job shutdown can lag ~20s after
  disconnect — next-session brief needs that settle, or an in-turn persist.
- **Learning:** live latency KPIs and forecast outcomes persist with provenance.
  Calibration-to-SkillBuilder promotion has not completed a production cycle.
- **Prediction:** Pythia runs off the spoken critical path. Proactive delivery
  remains disabled until consented delivery and calibration gates exist.
