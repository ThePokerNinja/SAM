# Samuel Phase 0 deploy helper — preflight, health checks, optional Render deploy hooks.
#
# Usage (from SAM repo root):
#   .\scripts\deploy-phase0.ps1 -Preflight     # typecheck + build + pytest
#   .\scripts\deploy-phase0.ps1 -CheckOnly     # prod health probes only
#   .\scripts\deploy-phase0.ps1 -Deploy        # POST deploy hooks (needs env vars)
#   .\scripts\deploy-phase0.ps1 -Preflight -Deploy -CheckOnly
#
# Deploy hooks: Render -> service -> Settings -> Deploy Hook (copy full URL incl. ?key=...)
# If hooks 404: regenerate hook in Render or use RENDER_API_KEY + SAM_*_SERVICE_ID.

param(
  [switch]$Preflight,
  [switch]$Deploy,
  [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$TokenUrl = if ($env:SAM_TOKEN_URL) { $env:SAM_TOKEN_URL.TrimEnd("/") } else { "https://sam-token.onrender.com" }
$PortalUrl = if ($env:SAM_PORTAL_URL) { $env:SAM_PORTAL_URL.TrimEnd("/") } else { "https://voice.michaelstewman.com" }

function Test-DeployHookUrl {
  param([string]$Url)
  if ([string]::IsNullOrWhiteSpace($Url)) { return $false }
  return $Url -match '^https://api\.render\.com/deploy/srv-[a-z0-9]+\?key='
}

function Invoke-RenderApiDeploy {
  param([string]$Name, [string]$ServiceId, [string]$ApiKey)
  if (-not $ServiceId -or -not $ApiKey) { return $false }
  Write-Host "Deploying $Name (Render API)..." -ForegroundColor Cyan
  try {
    $headers = @{
      Authorization  = "Bearer $ApiKey"
      Accept         = "application/json"
      "Content-Type" = "application/json"
    }
    $uri = "https://api.render.com/v1/services/$ServiceId/deploys"
    $res = Invoke-RestMethod -Method POST -Uri $uri -Headers $headers -Body '{"clearCache":"do_not_clear"}' -TimeoutSec 90
    Write-Host "[OK] $Name deploy $($res.id)" -ForegroundColor Green
    return $true
  } catch {
    Write-Host "[FAIL] $Name (Render API) - $($_.Exception.Message)" -ForegroundColor Red
    return $false
  }
}

function Invoke-DeployHook {
  param([string]$Name, [string]$HookUrl)
  $HookUrl = ($(if ($HookUrl) { $HookUrl } else { "" })).Trim()
  if (-not $HookUrl) {
    Write-Host "[skip] $Name - no hook URL" -ForegroundColor DarkGray
    return $false
  }
  if (-not (Test-DeployHookUrl $HookUrl)) {
    Write-Host "[FAIL] $Name - hook URL does not look like a Render deploy hook (expect https://api.render.com/deploy/srv-...?key=...)" -ForegroundColor Red
    return $false
  }
  Write-Host "Deploying $Name (hook)..." -ForegroundColor Cyan
  try {
    $res = Invoke-WebRequest -Method POST -Uri $HookUrl -UseBasicParsing -TimeoutSec 90
    Write-Host "[OK] $Name ($($res.StatusCode))" -ForegroundColor Green
    return $true
  } catch {
    $msg = $_.Exception.Message
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
      $code = [int]$_.Exception.Response.StatusCode
      $msg = "HTTP $code"
      if ($code -eq 404) {
        $msg += " - hook not found (regenerate in Render -> $Name -> Settings -> Deploy Hook; copy full URL)"
      }
    }
    Write-Host "[FAIL] $Name - $msg" -ForegroundColor Red
    return $false
  }
}

function Invoke-ServiceDeploy {
  param(
    [string]$Name,
    [string]$HookUrl,
    [string]$ServiceIdEnv,
    [string]$ApiKey
  )
  if (Invoke-DeployHook -Name $Name -HookUrl $HookUrl) { return $true }
  $serviceId = ($(if (Get-Item "Env:$ServiceIdEnv" -ErrorAction SilentlyContinue) { (Get-Item "Env:$ServiceIdEnv").Value } else { "" })).Trim()
  if ($serviceId -and $ApiKey) {
    return Invoke-RenderApiDeploy -Name $Name -ServiceId $serviceId -ApiKey $ApiKey
  }
  return $false
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

$deployOk = 0
$deployFail = 0

if ($Deploy) {
  Write-Host "=== Triggering Render deploys ===" -ForegroundColor Cyan
  $apiKey = ($(if ($env:RENDER_API_KEY) { $env:RENDER_API_KEY } else { "" })).Trim()
  $targets = @(
    @{ Name = "sam-token"; Hook = $env:SAM_TOKEN_DEPLOY_HOOK_URL; ServiceIdEnv = "SAM_TOKEN_SERVICE_ID" },
    @{ Name = "sam-agent"; Hook = $env:SAM_AGENT_DEPLOY_HOOK_URL; ServiceIdEnv = "SAM_AGENT_SERVICE_ID" },
    @{ Name = "sam-voice-portal"; Hook = $env:SAM_PORTAL_DEPLOY_HOOK_URL; ServiceIdEnv = "SAM_PORTAL_SERVICE_ID" }
  )
  $anyConfigured = $false
  foreach ($t in $targets) {
    $hook = ($(if ($t.Hook) { $t.Hook } else { "" })).Trim()
    $sid = ($(if (Get-Item "Env:$($t.ServiceIdEnv)" -ErrorAction SilentlyContinue) { (Get-Item "Env:$($t.ServiceIdEnv)").Value } else { "" })).Trim()
    if ($hook -or ($sid -and $apiKey)) { $anyConfigured = $true }
    if (Invoke-ServiceDeploy -Name $t.Name -HookUrl $hook -ServiceIdEnv $t.ServiceIdEnv -ApiKey $apiKey) {
      $deployOk++
    } elseif ($hook -or ($sid -and $apiKey)) {
      $deployFail++
    }
  }
  if (-not $anyConfigured) {
    Write-Host "No deploy hooks or API service IDs set. Push to GitHub (auto-deploy) or configure hooks." -ForegroundColor Yellow
    Write-Host "  Hooks: SAM_TOKEN_DEPLOY_HOOK_URL, SAM_AGENT_DEPLOY_HOOK_URL, SAM_PORTAL_DEPLOY_HOOK_URL" -ForegroundColor DarkGray
    Write-Host "  API:   RENDER_API_KEY + SAM_*_SERVICE_ID (from Render dashboard URL)" -ForegroundColor DarkGray
  } elseif ($deployFail -gt 0) {
    Write-Host ""
    Write-Host "Some deploys failed. If hooks return 404, regenerate each hook in Render (Settings -> Deploy Hook)." -ForegroundColor Yellow
    Write-Host "Git push to master may still auto-deploy if enabled on each service." -ForegroundColor DarkGray
  }
  if ($deployFail -gt 0 -and $deployOk -eq 0) { exit 1 }
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
      Write-Host "[FAIL] $($pair.Name) $($pair.Url) - $($_.Exception.Message)" -ForegroundColor Red
    }
  }
  Write-Host ""
  Write-Host "Voice portal: $PortalUrl" -ForegroundColor Green
  Write-Host "Token server: $TokenUrl" -ForegroundColor Green
}
