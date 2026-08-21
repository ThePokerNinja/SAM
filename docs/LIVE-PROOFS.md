# Live proofs — what to say on the call

Run against production after sam-agent is on the SHA under test.

## Automated (agent)

From the SAM repo:

```
.\scripts\run-golden-path.ps1
```

That covers pack activation (SAM-039 already live). For artifacts (SAM-043/044) use the write then recall manifests with `--owner-test-token` and confirm `prior_artifact_brief` has count > 0.

## Physical (operator)

1. **SAM-038 / 045** — Call the Samuel number. Say "pause this conversation", then "resume". Confirm he stops and restarts. Hang up. Session summary should exist.
2. **SAM-042 / 046 + Moderator** — Join voice.michaelstewman.com with a second person. Say "Samuel, moderate this disagreement." Each person states a position. Confirm he does not take a side and can pause.
3. **Wave 7 appointment** — "Switch to scheduling mode" then book a real calendar slot. Confirm the event on Google Calendar.
4. **SAM-070** — Interrupt him mid-sentence. Then `.\scripts\read-latest-barge-in.ps1` from rainMaker. Look for `inbound_detect_at_ms` vs `playback_stop_at_ms` in sam-agent logs.

Do not mark these Done from a unit test.
