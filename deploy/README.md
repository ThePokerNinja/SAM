# Samuel Phase 0 � Render deploy

Deploys three services from this repo:

| Service | Role | Public URL |
|---------|------|------------|
| **sam-voice-portal** | Static React portal | `https://voice.michaelstewman.com` (custom domain) |
| **sam-token** | LiveKit JWT minting | `https://sam-token.onrender.com` |
| **sam-agent** | LiveKit Agents worker (private) | none � registers with LiveKit Cloud |

## Prerequisites

- LiveKit Cloud project (e.g. `atlas`) with API key + secret
- Groq API key (brain: `openai/gpt-oss-20b`; the former 8b model is no longer available)
- Deepgram API key (direct Nova/Flux STT; avoids LiveKit Inference inactivity closure)
- ElevenLabs API key + Samuel `SAM_VOICE_ID`
- GitHub repo: `ThePokerNinja/SAM`
- DNS access for `voice.michaelstewman.com`

## First-time Render setup

### 1. Push code

Commit and push `render.yaml`, `deploy/`, and portal/worker changes to `master`.

### 2. Create Blueprint

1. Render Dashboard ? **New** ? **Blueprint**
2. Connect `ThePokerNinja/SAM`, branch `master`
3. **Apply** � creates `sam-token`, `sam-voice-portal`, `sam-agent`

### 3. Set secrets

On **sam-token** and **sam-agent** (Environment):

| Variable | Required | Notes |
|----------|----------|-------|
| `LIVEKIT_URL` | yes | `wss://�.livekit.cloud` |
| `LIVEKIT_API_KEY` | yes | |
| `LIVEKIT_API_SECRET` | yes | |
| `DEEPGRAM_API_KEY` | yes | agent only |
| `GROQ_API_KEY` | yes | agent only |
| `ELEVENLABS_API_KEY` | yes | agent only |
| `SAM_VOICE_ID` | yes | agent only |
| `SAM_PORTAL_ACCESS_KEY` | recommended | sam-token only � owner secret-link gate |

Optional: `OPENAI_API_KEY` if not using Groq.

**Owner portal gate (no login UI):** set `SAM_PORTAL_ACCESS_KEY` on **sam-token** to a long random string. Bookmark once (use `#access=` so base64 `+` is safe):

`https://voice.michaelstewman.com/#access=<your-key>`

Or query with URL encoding: `?access=` + encodeURIComponent(key). The key is saved locally and the URL is cleaned without a refresh. Others see the candle, then **Access denied** on click. Leave unset for local dev.

### 4. Custom domain

1. **sam-voice-portal** ? Settings ? **Custom Domains**
2. Add `voice.michaelstewman.com`
3. Add the CNAME Render provides at your DNS host (same pattern as other Render custom domains)

### 5. CORS on token server

After the portal URL is known, set on **sam-token**:

```
SAM_ALLOWED_ORIGINS=https://voice.michaelstewman.com,https://sam-voice-portal.onrender.com
```

(Comma-separated, no spaces.)

### 6. Re-deploy portal

Trigger a manual deploy on **sam-voice-portal** so `VITE_TOKEN_URL` picks up the live `sam-token` URL.

### 7. Verify

```powershell
# From SAM repo root
.\scripts\deploy-phase0.ps1 -CheckOnly

# Or manually:
Invoke-WebRequest https://sam-token.onrender.com/health -UseBasicParsing
Invoke-WebRequest https://voice.michaelstewman.com -UseBasicParsing
```

Open `https://voice.michaelstewman.com` on phone/desktop (not `?preview=1`). Click candle ? connect ? speak. Hard-refresh if JS looks stale.

## Local preflight

```powershell
.\scripts\deploy-phase0.ps1 -Preflight
```

Runs client typecheck + build and worker pytest.

## Redeploy after changes

- **Git auto-deploy** if enabled on each service
- Or deploy hooks / `.\scripts\deploy-phase0.ps1 -Deploy` (needs hook URLs in env)

### Blueprint env vs deploy hook (Wave 8.1)

A **deploy hook** rebuilds the current service. It does **not** sync `render.yaml` env
onto the dashboard:

- Keys **already set** keep the dashboard value (Wave 8.1: `SAM_ENDPOINTING_MAX` shipped
  0.6, prod kept 1.2 — the 777ms EOU floor).
- Keys that exist **only in yaml** stay unset (Wave 2.1: `SAM_MEMORY_ENABLED` and
  `SAM_CACHE_DIR` were never on sam-agent, so session artifacts never wrote).

Code defaults only win when the var is **unset**. PUT new keys with
`.\scripts\set-sam-agent-env.ps1`, then `.\scripts\verify-sam-agent.ps1 -Wait`.

After changing a non-secret in `render.yaml`:

1. Confirm the live value on Render → **sam-agent** → Environment (or
   `.\scripts\verify-sam-agent.ps1` / the `Samuel starting |` worker log).
2. If it is missing or stale, PUT the dashboard value or sync the Blueprint, then redeploy.
3. Do not treat “hook returned 200” as “new env is live.”

Wave 8.2+ (Phase 5.0): voice canonical brain is **OpenAI** (`SAM_BRAIN=openai`).
Auto-detect prefers OpenAI when both `OPENAI_API_KEY` and `GROQ_API_KEY` are set.
Pin `SAM_BRAIN=groq` only for lab/bench arms — not production while Groq Developer
is unavailable.

Wave 8.3: use ``.\scripts\verify-sam-agent.ps1 -Wait`` (needs ``RENDER_API_KEY`` +
``SAM_AGENT_SERVICE_ID``). Hook 200 is not proof the build is live or that env changed.
``deploy-sam-agent.ps1 -Wait`` polls until status is ``live`` and prints live env
(including ``SAM_MEMORY_ENABLED`` / ``SAM_CACHE_DIR``).

### Artifact persist across rooms (Wave 2.1)

LiveKit Agents uses **one process per job**. After the bench client disconnects, the
write job can take ~20s to reach ``process exiting``. Session-close SQLite persist
may not be visible to the next room until then. ``.\scripts\run-artifact-proof.ps1``
defaults to a **35s** settle; 8s produced ``prior_artifact_brief_empty``.

### Deploy hook env vars (optional)

Copy the **full** URL from Render -> **that service** -> **Settings** -> **Deploy Hook** (must include `?key=...`).

Use the URL **exactly as copied** — do not wrap it in a template:

```powershell
# WRONG (nested template + real URL):
# $env:SAM_TOKEN_DEPLOY_HOOK_URL = 'https://api.render.com/deploy/srv-XXXX?key=https://api.render.com/deploy/srv-abc?key=xyz'

# RIGHT (paste Render's copy button output only):
$env:SAM_TOKEN_DEPLOY_HOOK_URL = 'https://api.render.com/deploy/srv-abc123?key=yourSecretKey'
```

Each service has its **own** hook — repeat for `sam-token`, `sam-agent`, and `sam-voice-portal`.

**API fallback** (same pattern as rainmaker-api):

```powershell
$env:RENDER_API_KEY = '<Render account API key>'
$env:SAM_TOKEN_SERVICE_ID = 'srv-...'   # from Render dashboard URL
$env:SAM_AGENT_SERVICE_ID = 'srv-...'
$env:SAM_PORTAL_SERVICE_ID = 'srv-...'
.\scripts\deploy-phase0.ps1 -Deploy
```

## Prod v2v baseline

After first successful voice session, capture worker logs on **sam-agent** (Render ? Logs):

```
V2V turn �: eou=�ms + ttft=�ms + ttfb=�ms = �ms
```

Record p50/p95 in `rainMaker/docs/todos/SAMUEL-NEXT-STEPS-BACKLOG.md`.

## Decommission old Charles PWA

Once Samuel is signed off on prod:

1. Point `voice.michaelstewman.com` only at **sam-voice-portal** (already if custom domain added here)
2. Archive `ThePokerNinja/charles` `voice_pwa/` � do not dual-run voice products

**Cost note:** Hobby workspaces cannot use autoscaling in `render.yaml` (single `sam-agent` instance). Upgrade workspace or remove any `scaling:` block if sync fails.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `token request failed` | Check `VITE_TOKEN_URL` on portal build; `sam-token` health; CORS origins |
| Portal loads, no Samuel voice | `sam-agent` logs; LiveKit credentials; worker registered? |
| `Failed to fetch` on token | Add portal origin to `SAM_ALLOWED_ORIGINS` |
| Candle shows Access denied | Set `SAM_PORTAL_ACCESS_KEY` on sam-token; open bookmark with `?access=` |
| Agent hears itself (console) | Expected without WebRTC AEC � test in browser with mic |
