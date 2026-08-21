# Live agent-OS evidence

## 2026-08-21 production close

- Runtime SHA: `2f80e882b843` (`sam-agent`, Render).
- SAM-039: production audio activated Moderator, Appointment, and SkillBuilder packs.
- SAM-040/041: owner-role production sessions wrote and recalled `ultramarine`
  across separate LiveKit rooms on `9af52040eb31`.
- SAM-043/044: **Partial**. Prior-session recall succeeds, but the benchmark did
  not receive `prior_artifact_brief`; canonical owner memory can explain the
  answer. Keep this ticket open until artifact-source telemetry is observed.
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
  place. Retention/deletion policy and artifact-source live proof remain open.
- **Learning:** live latency KPIs and forecast outcomes persist with provenance.
  Calibration-to-SkillBuilder promotion has not completed a production cycle.
- **Prediction:** Pythia runs off the spoken critical path. Proactive delivery
  remains disabled until consented delivery and calibration gates exist.
