# Outbound SIP: Samuel calls the owner (REVIEW)

Texting `REVIEW` to the toll-free number makes rm_api call `POST /dial` on sam-agent, which
mints a `samuel-dial-*` room and SIP-dials the owner. Until the outbound trunk exists the worker
answers `outbound_not_configured` and rm_api texts back:

> I can't dial out yet. Call me at 855-634-3880 and say review; I'll start with Charles's update.

Both paths land in the same review (digest first, decisions drafted, one `YES <code>` text after).

## Who does what

| Step | Owner | Tool |
|---|---|---|
| 1. Twilio Elastic SIP trunk (termination) | operator, Twilio console | by hand |
| 2. LiveKit outbound trunk | agent or operator | `.\scripts\provision-sam-outbound.ps1 -Address …` |
| 3. Render env on sam-agent | agent or operator | `… -PushRender`, then `deploy-sam-agent.ps1`, `verify-sam-agent.ps1 -Wait` |
| 4. Lab proof (no phone) | agent | `… -LabProof -DialUrl https://<sam-agent-host>/dial` |
| 5. One phone proof | operator | text `REVIEW` |

Agents do not do step 1 or step 5. One failed proof ends the list (`samuel-live-call-gate.mdc`).

## 1. Twilio console (operator, ~10 min)

Elastic SIP Trunking -> Trunks -> **Create** `samuel-outbound`.

- **Termination**: pick a SIP URI, e.g. `samuel.pstn.twilio.com`. Copy the full host; that is
  `SAM_SIP_OUTBOUND_ADDRESS`.
- **Termination -> Authentication -> Credential Lists**: reuse the inbound pilot entry
  (`sam-inbound` + the `SAM_SIP_AUTH_PASSWORD` already in `worker/.env`). If you make a new one,
  keep the password alphanumeric; it is interpolated into SIP URIs.
- **Termination -> IP ACL**: leave empty (credential auth) unless LiveKit's egress IPs are
  published for your region; then add them.
- **Numbers**: attach `+1 855 634 3880` so the owner's phone shows the same number they text.
- **Origination**: nothing. The inbound pilot keeps its own trunk.

Geo permissions: Voice -> Settings -> Geo permissions must allow US outbound (it does for
the toll-free number already).

## 2. LiveKit outbound trunk

From the SAM repo root:

```powershell
.\scripts\provision-sam-outbound.ps1 -Address samuel.pstn.twilio.com
```

Idempotent. Creates or reconciles the LiveKit trunk named `Samuel pilot outbound`, caller ID
`SAM_SIP_PILOT_NUMBER` (override with `-CallerId +1…`), and writes
`SAM_SIP_OUTBOUND_TRUNK_ID=ST_…` into `worker/.env`. Nothing secret is printed.

## 3. Render env

`render.yaml` does not push values onto the dashboard (Wave 8.1 / Wave 2.1 lesson), so PUT them:

```powershell
.\scripts\provision-sam-outbound.ps1 -PushRender
.\scripts\deploy-sam-agent.ps1
.\scripts\verify-sam-agent.ps1 -Wait
```

Watch list after deploy: `SAM_SIP_OUTBOUND_TRUNK_ID`, `SAM_SIP_OWNER_NUMBERS`, `LIVEKIT_URL`,
`LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `SAM_AGENT_NAME` (explicit dispatch needs it).

rm_api side (already live): `SAM_DIAL_URL` or `SAM_HERO_SNAPSHOT_URL` on rainmaker-api points at
the sam-agent health listener. `RM_ALERT_TO` is the number REVIEW dials.

## 4. Lab proof (no phone rings)

```powershell
.\scripts\provision-sam-outbound.ps1 -LabProof
```

sam-agent is a private Render service, so the proof goes through rm_api:

1. `GET /ops/place-call/status` (cron token, read from Render, never printed) returns the
   worker's `/health` view: `workerGit`, `outboundConfigured`, `dialDryRun`. The script stops
   unless `dialDryRun` is true, because an older worker would treat the next step as a real call.
2. `POST /ops/place-call` with `{"number": <owner>, "dry_run": true, "spoken": "review"}`.
   The worker runs `can_dial` (E.164, allow-list, trunk + LiveKit creds) and returns
   `{"ok": true, "dryRun": true}` **before** creating a room. Nothing rings.

Read the result:

- `"dryRun": true` = PASS.
- `outbound_not_configured` = `SAM_SIP_OUTBOUND_TRUNK_ID` or `LIVEKIT_*` missing on the running
  instance. Re-run `verify-sam-agent.ps1 -Wait`.
- `"room": …` in the body = the server ignored `dry_run` and placed a real call; the worker or
  rm_api is on an older SHA. Do not repeat; redeploy first.
- no HTTP response = wrong URL; the request never left the machine.

Note `number_not_allowlisted` on its own proves nothing about the trunk: `can_dial` checks the
allow-list first. That is why the dry run uses the owner's number.

Worker unit coverage: `worker/tests/test_review_call.py` (review leg metadata, opener, tools, dry
run) and `worker/tests/test_foundation_21.py` (outbound allow-list).

State on 2026-10-03: the LiveKit trunk `Samuel pilot outbound` already exists
(`scs-samuel-outbound.pstn.twilio.com`, caller ID +1 855 634 3880) and `SAM_SIP_OUTBOUND_TRUNK_ID`,
`SAM_SIP_OWNER_NUMBERS`, `SAM_SIP_OUTBOUND_ALLOWED` are on the sam-agent dashboard. Step 1 and 2 are
done; what remains is the dry-run proof after both services deploy, then one phone proof.

## 5. One phone proof (operator)

Text `REVIEW`. Expected:

1. Reply within ~8 s: `Calling you now. I'll open with what Charles has been up to.`
2. Phone rings from 855-634-3880. On "hello", Samuel reads the digest and asks where to start.
3. Say `accept <idea>`; Samuel repeats it back, then "Noted … Nothing moves until you text YES".
4. Say `wrap up`; Samuel: "I texted you the list; reply YES with the code to commit it."
5. SMS arrives: `Review done. Accepted: … Reply YES <code> to commit, NO <code> to drop.`
6. Reply `YES <code>`: `Committed <code>. …`; `/ops/proposals` shows the lane moves.

If the call drops mid-review, rm_api auto-finishes after `RM_REVIEW_IDLE_S` (120 s) and texts the
same list prefixed with "The call dropped before we wrapped up".

Pull worker logs after the call (`review call detected`, `outbound first speech=human`) before
deciding anything. One proof per call.

## What can go wrong

| Symptom | Cause | Fix |
|---|---|---|
| `I can't dial out yet` text | trunk id not on the live instance | step 3; confirm with `-LabProof` |
| `I couldn't place the call (TwirpError …)` | Twilio rejected the INVITE: credential, geo permission, or caller ID not on the trunk | Twilio -> Monitor -> Logs -> SIP; fix in console; rerun step 2 to reconcile |
| Rings, answers, silence | `SAM_AGENT_NAME` unset so no dispatch; or the owner gate failed (`SAM_SIP_OWNER_NUMBERS` missing the dialed number) | set env, redeploy; the review leg keeps tools on but every tool is owner-gated |
| Samuel talks like a guest call | metadata arrived without `spoken: review` | rm_api `_review_call_sms` sets `spoken="review"`, `brief="review: …"`; check rm_api SHA |
| Decisions "committed" from voice | impossible by design; `draft_decision` only writes to the review session; lanes move on `YES <code>` | if you see a lane move without a code, that is a bug; file it |
