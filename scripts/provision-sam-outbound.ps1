# Provision Samuel's outbound SIP leg for the REVIEW call (rm_api -> /dial -> owner's phone).
#
# What this does (idempotent, no secrets printed):
#   1. Checks worker/.env for the Twilio Elastic SIP termination host and the shared credential.
#   2. Creates or reconciles the LiveKit outbound trunk "Samuel pilot outbound".
#   3. Writes SAM_SIP_OUTBOUND_TRUNK_ID into worker/.env.
#   4. With -PushRender, PUTs SAM_SIP_OUTBOUND_TRUNK_ID (and SAM_SIP_OWNER_NUMBERS if present)
#      onto the sam-agent Render service, then prints the verify command.
#   5. With -LabProof, POSTs {"dry_run": true} for the owner's number. The worker runs the
#      allow-list and trunk checks and stops; nothing rings. PASS = {"ok":true,"dryRun":true}.
#
# What the operator does by hand first (see docs/runbooks/sip-outbound.md):
#   Twilio Console -> Elastic SIP Trunking -> Trunks -> create "samuel-outbound"
#     Termination: SIP URI  <name>.pstn.twilio.com      -> SAM_SIP_OUTBOUND_ADDRESS
#     Termination: Credential List = sam-inbound / SAM_SIP_AUTH_PASSWORD (same as inbound pilot)
#     Numbers: attach +1 855 634 3880 (caller ID)
#
# Usage (from SAM repo root):
#   .\scripts\provision-sam-outbound.ps1 -Address samuel.pstn.twilio.com
#   .\scripts\provision-sam-outbound.ps1 -PushRender
#   .\scripts\provision-sam-outbound.ps1 -LabProof -DialUrl https://rainmaker-api-waqs.onrender.com/ops/place-call
#   (sam-agent is a private Render service; rm_api's /ops/place-call proxies /dial with the cron token.
#    Pass -DialUrl http://<host>:8080/dial to hit a worker directly, e.g. a local one.)

param(
    [string]$Address = "",
    [string]$CallerId = "",
    [switch]$PushRender,
    [switch]$LabProof,
    [string]$DialUrl = ""
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $root "worker\.env"
if (-not (Test-Path $EnvPath)) { throw "worker/.env not found at $EnvPath; run set-sam-sip-env.ps1 first" }

function Get-EnvValue([string]$Key) {
    $line = Get-Content $EnvPath | Where-Object { $_ -match "^\s*$([regex]::Escape($Key))=" } | Select-Object -First 1
    if (-not $line) { return "" }
    return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
}

function Set-EnvValue([string]$Key, [string]$Value) {
    $lines = @(Get-Content $EnvPath)
    $pattern = "^\s*$([regex]::Escape($Key))="
    if ($lines -match $pattern) {
        $lines = $lines | ForEach-Object { if ($_ -match $pattern) { "$Key=$Value" } else { $_ } }
    } else {
        $lines += "$Key=$Value"
    }
    Set-Content -Path $EnvPath -Value $lines -Encoding UTF8
}

if ($Address) { Set-EnvValue "SAM_SIP_OUTBOUND_ADDRESS" $Address }
if ($CallerId) { Set-EnvValue "SAM_SIP_OUTBOUND_NUMBER" $CallerId }

$address = Get-EnvValue "SAM_SIP_OUTBOUND_ADDRESS"
if (-not $address) {
    Write-Host "SAM_SIP_OUTBOUND_ADDRESS is not set." -ForegroundColor Yellow
    Write-Host "  Create the Twilio Elastic SIP trunk first (docs/runbooks/sip-outbound.md), then rerun:" -ForegroundColor Yellow
    Write-Host "  .\scripts\provision-sam-outbound.ps1 -Address <name>.pstn.twilio.com" -ForegroundColor Yellow
    exit 2
}
foreach ($key in @("SAM_SIP_AUTH_USERNAME", "SAM_SIP_AUTH_PASSWORD", "SAM_SIP_PILOT_NUMBER", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")) {
    if (-not (Get-EnvValue $key)) { throw "$key missing from worker/.env; run .\scripts\set-sam-sip-env.ps1 first" }
}

# --- 1. LiveKit outbound trunk ----------------------------------------------------------
$py = Join-Path $PSScriptRoot "provision-sam-outbound.py"
$out = & python $py 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host "  $_" }
if ($code -ne 0) { throw "provision-sam-outbound.py exited $code" }
$trunkLine = $out | Where-Object { $_ -match "^SAM_SIP_OUTBOUND_TRUNK_ID=" } | Select-Object -Last 1
if (-not $trunkLine) { throw "trunk id line not found in script output" }
$trunkId = ($trunkLine -split "=", 2)[1].Trim()
Set-EnvValue "SAM_SIP_OUTBOUND_TRUNK_ID" $trunkId
Write-Host "worker/.env: SAM_SIP_OUTBOUND_TRUNK_ID = $trunkId" -ForegroundColor Green

# --- 2. Render env (dashboard values do not sync from render.yaml) ---------------------
if ($PushRender) {
    & (Join-Path $PSScriptRoot "set-sam-agent-env.ps1") -Key SAM_SIP_OUTBOUND_TRUNK_ID -Value $trunkId
    if (Get-EnvValue "SAM_SIP_OWNER_NUMBERS") {
        & (Join-Path $PSScriptRoot "set-sam-agent-env.ps1") -Key SAM_SIP_OWNER_NUMBERS -ValueFromDotEnv $EnvPath
    }
    Write-Host ""
    Write-Host "Now redeploy and confirm the live SHA + env watch list:" -ForegroundColor Cyan
    Write-Host "  .\scripts\deploy-sam-agent.ps1" -ForegroundColor Cyan
    Write-Host "  .\scripts\verify-sam-agent.ps1 -Wait" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "Not pushed to Render. When ready:" -ForegroundColor Yellow
    Write-Host "  .\scripts\provision-sam-outbound.ps1 -PushRender" -ForegroundColor Yellow
}

# --- 3. Lab proof: dry run for the owner's number. The worker checks allow-list + trunk and
#        returns before creating a room, so no phone rings. ------------------------------------
if ($LabProof) {
    $owner = ((Get-EnvValue "SAM_SIP_OWNER_NUMBERS") -split ",")[0].Trim()
    if (-not $owner) { throw "SAM_SIP_OWNER_NUMBERS is empty in worker/.env; the dry run needs an allow-listed number" }
    if (-not $DialUrl) {
        $DialUrl = ($(if ($env:SAM_DIAL_URL) { $env:SAM_DIAL_URL } else { "https://rainmaker-api-waqs.onrender.com/ops/place-call" })).Trim()
    }
    $headers = @{ "Content-Type" = "application/json" }
    if ($DialUrl -match "/ops/place-call") {
        # rm_api proxies to the private worker; it wants the cron token. Pull it from Render, never print it.
        $renderKey = [Environment]::GetEnvironmentVariable("RENDER_API_KEY", "User")
        if (-not $renderKey) { $renderKey = $env:RENDER_API_KEY }
        if (-not $renderKey) { throw "RENDER_API_KEY is needed to read RM_CRON_TOKEN for the rm_api proxy" }
        $rh = @{ Authorization = "Bearer $renderKey"; Accept = "application/json" }
        $rows = Invoke-RestMethod -Uri "https://api.render.com/v1/services/srv-d8e1sk4m0tmc73eeq42g/env-vars?limit=100" -Headers $rh -TimeoutSec 30
        $cron = ""
        foreach ($row in $rows) { $item = if ($row.envVar) { $row.envVar } else { $row }; if ([string]$item.key -eq "RM_CRON_TOKEN") { $cron = [string]$item.value } }
        if (-not $cron) { throw "RM_CRON_TOKEN missing on rainmaker-api" }
        $headers["X-RM-CRON-TOKEN"] = $cron
    }
    if ($DialUrl -match "/ops/place-call") {
        # Refuse to send a dry run to a worker that would treat it as a real call.
        $statusUrl = ($DialUrl -replace "/ops/place-call.*$", "/ops/place-call/status")
        try {
            $st = Invoke-RestMethod -Uri $statusUrl -Headers $headers -TimeoutSec 30
        } catch {
            throw "Could not read $statusUrl ($($_.Exception.Message)). rm_api may predate the status route; redeploy rm_api first."
        }
        Write-Host "worker status -> git=$($st.workerGit) outboundConfigured=$($st.outboundConfigured) dialDryRun=$($st.dialDryRun)"
        if (-not $st.ok) { throw "worker status not ok: $($st.error)" }
        if (-not $st.dialDryRun) { throw "The live worker does not advertise dialDryRun; a dry run there would ring the phone. Deploy sam-agent and rerun verify-sam-agent.ps1 -Wait." }
        if (-not $st.outboundConfigured) {
            Write-Host "FAIL: worker reports outboundConfigured=false. SAM_SIP_OUTBOUND_TRUNK_ID or LIVEKIT_* is missing on the running instance." -ForegroundColor Red
            exit 1
        }
    }
    $body = @{ number = $owner; brief = "review: lab proof"; spoken = "review"; notify_owner = $false; dry_run = $true } | ConvertTo-Json
    try {
        $r = Invoke-WebRequest -Uri $DialUrl -Method POST -Headers $headers -Body $body -UseBasicParsing -TimeoutSec 45
        $status = [int]$r.StatusCode; $content = $r.Content
    } catch {
        $resp = $_.Exception.Response
        if (-not $resp) { throw "No HTTP response from $DialUrl - request never reached the server: $($_.Exception.Message)" }
        $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $status = [int]$resp.StatusCode; $content = $sr.ReadToEnd()
    }
    $shown = $content -replace [regex]::Escape($owner), ("..." + $owner.Substring([Math]::Max(0, $owner.Length - 4)))
    Write-Host "lab dry run -> HTTP $status $shown"
    if ($content -match '"dryRun"\s*:\s*true') {
        Write-Host "PASS: the live worker has the trunk and the allow-list; nothing rang." -ForegroundColor Green
        Write-Host "Next: one phone proof. Text REVIEW to the toll-free number; expect 'Calling you now.' then a ring." -ForegroundColor Green
    } elseif ($content -match "outbound_not_configured") {
        Write-Host "FAIL: worker still reports outbound_not_configured. Env not live on the running instance; rerun verify-sam-agent.ps1 -Wait." -ForegroundColor Red
        exit 1
    } elseif ($content -match '"room"') {
        Write-Host "WARNING: the server ignored dry_run and placed a real call. The worker or rm_api is on an older SHA; redeploy before another proof." -ForegroundColor Red
        exit 1
    } else {
        Write-Host "Unexpected body; read it before placing a phone proof." -ForegroundColor Yellow
        exit 1
    }
}
