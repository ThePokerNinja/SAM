# Samuel Phase 0 deploy helper — preflight, health checks, optional Render deploy hooks.
#
# Usage (from SAM repo root):
#   .\scripts\deploy-phase0.ps1 -Preflight     # typecheck + build + pytest
#   .\scripts\deploy-phase0.ps1 -CheckOnly     # prod health probes only
#   .\scripts\deploy-phase0.ps1 -Deploy        # POST deploy hooks (needs env vars)
#   .\scripts\deploy-phase0.ps1 -Preflight -Deploy -CheckOnly

param(
  [switch]$Preflight,
  [switch]$Deploy,
  [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$TokenUrl = if ($env:SAM_TOKEN_URL) { $env:SAM_TOKEN_URL.TrimEnd("/") } else { "https://sam-token.onrender.com" }
$PortalUrl = if ($env:SAM_PORTAL_URL) { $env:SAM_PORTAL_URL.TrimEnd("/") } else { "https://voice.michaelstewman.com" }

function Invoke-DeployHook {
  param([string]$Name, [string]$HookUrl)
  if (-not $HookUrl) {
    Write-Host "[skip] $Name — no hook URL" -ForegroundColor DarkGray
    return
  }
  Write-Host "Deploying $Name..." -ForegroundColor Cyan
  $res = Invoke-WebRequest -Method POST -Uri $HookUrl -UseBasicParsing -TimeoutSec 90
  Write-Host "[OK] $Name ($($res.StatusCode))" -ForegroundColor Green
}

if ($Preflight) {
  Write-Host "=== Samuel preflight ===" -ForegroundColor Cyan
  Push-Location (Join-Path $Root "client")
  try {
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $env:VITE_TOKEN_URL = $TokenUrl
    npm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  } finally {
    Pop-Location
  }
  Push-Location (Join-Path $Root "worker")
  try {
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  } finally {
    Pop-Location
  }
  Write-Host "[OK] Preflight passed" -ForegroundColor Green
}

if ($Deploy) {
  Write-Host "=== Triggering Render deploy hooks ===" -ForegroundColor Cyan
  Invoke-DeployHook "sam-token" $env:SAM_TOKEN_DEPLOY_HOOK_URL
  Invoke-DeployHook "sam-agent" $env:SAM_AGENT_DEPLOY_HOOK_URL
  Invoke-DeployHook "sam-voice-portal" $env:SAM_PORTAL_DEPLOY_HOOK_URL
  if (-not $env:SAM_TOKEN_DEPLOY_HOOK_URL -and -not $env:SAM_AGENT_DEPLOY_HOOK_URL -and -not $env:SAM_PORTAL_DEPLOY_HOOK_URL) {
    Write-Host "No deploy hooks set. Push to GitHub or set SAM_*_DEPLOY_HOOK_URL." -ForegroundColor Yellow
  }
}

if ($CheckOnly -or (-not $Preflight -and -not $Deploy)) {
  Write-Host "=== Prod health checks ===" -ForegroundColor Cyan
  foreach ($pair in @(
    @{ Name = "sam-token"; Url = "$TokenUrl/health" },
    @{ Name = "portal"; Url = $PortalUrl }
  )) {
    try {
      $r = Invoke-WebRequest -Uri $pair.Url -UseBasicParsing -TimeoutSec 20
      Write-Host "[OK] $($pair.Name) $($pair.Url) ($($r.StatusCode))" -ForegroundColor Green
    } catch {
      Write-Host "[FAIL] $($pair.Name) $($pair.Url) — $($_.Exception.Message)" -ForegroundColor Red
    }
  }
  Write-Host ""
  Write-Host "Voice portal: $PortalUrl" -ForegroundColor Green
  Write-Host "Token server: $TokenUrl" -ForegroundColor Green
}
