# Samuel Phase 0 � Render deploy

Deploys three services from this repo:

| Service | Role | Public URL |
|---------|------|------------|
| **sam-voice-portal** | Static React portal | `https://voice.michaelstewman.com` (custom domain) |
| **sam-token** | LiveKit JWT minting | `https://sam-token.onrender.com` |
| **sam-agent** | LiveKit Agents worker (private) | none � registers with LiveKit Cloud |

## Prerequisites

- LiveKit Cloud project (e.g. `atlas`) with API key + secret
- Groq API key (brain: `llama-3.1-8b-instant`)
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
| `GROQ_API_KEY` | yes | agent only |
| `ELEVENLABS_API_KEY` | yes | agent only |
| `SAM_VOICE_ID` | yes | agent only |
| `SAM_PORTAL_ACCESS_KEY` | recommended | sam-token only � owner secret-link gate |

Optional: `OPENAI_API_KEY` if not using Groq.

**Owner portal gate (no login UI):** set `SAM_PORTAL_ACCESS_KEY` on **sam-token** to a long random string. Bookmark once:

`https://voice.michaelstewman.com/?access=<your-key>`

The key is saved locally and the URL is cleaned without a refresh. Others see the candle, then **Access denied** on click. Leave unset for local dev.

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

### Deploy hook env vars (optional)

```powershell
$env:SAM_TOKEN_DEPLOY_HOOK_URL = '<sam-token hook>'
$env:SAM_PORTAL_DEPLOY_HOOK_URL = '<sam-voice-portal hook>'
$env:SAM_AGENT_DEPLOY_HOOK_URL = '<sam-agent hook>'
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
