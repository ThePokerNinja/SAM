# Trigger a Render deploy for sam-voice-portal (voice.michaelstewman.com).
# Usage (from SAM repo root):
#   .\scripts\deploy-sam-portal-render.ps1
#   .\scripts\deploy-sam-portal-render.ps1 -Wait
#
# Configure ONE of:
#   SAM_PORTAL_DEPLOY_HOOK_URL  - Deploy Hook from Render -> sam-voice-portal -> Settings
#   RENDER_API_KEY + SAM_PORTAL_SERVICE_ID - API deploy (service id from dashboard URL)

param(
  [switch]$Wait,
  [int]$WaitTimeoutSec = 600
)

$ErrorActionPreference = "Stop"
$PortalUrl = if ($env:SAM_PORTAL_URL) { $env:SAM_PORTAL_URL.TrimEnd("/") } else { "https://voice.michaelstewman.com" }

function Invoke-PortalDeploy {
  $hook = ($(if ($env:SAM_PORTAL_DEPLOY_HOOK_URL) { $env:SAM_PORTAL_DEPLOY_HOOK_URL } else { "" })).Trim()
  if ($hook) {
    Write-Host "Triggering sam-voice-portal deploy (deploy hook)..." -ForegroundColor Cyan
    $res = Invoke-WebRequest -Method POST -Uri $hook -UseBasicParsing -TimeoutSec 60
    Write-Host "Deploy hook OK ($($res.StatusCode))" -ForegroundColor Green
    return
  }

  $apiKey = ($(if ($env:RENDER_API_KEY) { $env:RENDER_API_KEY } else { "" })).Trim()
  $serviceId = ($(if ($env:SAM_PORTAL_SERVICE_ID) { $env:SAM_PORTAL_SERVICE_ID } else { "" })).Trim()
  if ($apiKey -and $serviceId) {
    Write-Host "Triggering sam-voice-portal deploy (API) for service $serviceId..." -ForegroundColor Cyan
    $headers = @{
      Authorization  = "Bearer $apiKey"
      Accept         = "application/json"
      "Content-Type" = "application/json"
    }
    $body = '{"clearCache":"do_not_clear"}'
    $uri = "https://api.render.com/v1/services/$serviceId/deploys"
    $res = Invoke-RestMethod -Method POST -Uri $uri -Headers $headers -Body $body -TimeoutSec 60
    Write-Host "Deploy started: $($res.id)" -ForegroundColor Green
    return
  }

  Write-Host ""
  Write-Host "sam-voice-portal deploy not configured." -ForegroundColor Red
  Write-Host "Set ONE of:" -ForegroundColor Yellow
  Write-Host "  `$env:SAM_PORTAL_DEPLOY_HOOK_URL = '<hook from Render -> sam-voice-portal -> Deploy Hook>'"
  Write-Host "  OR `$env:RENDER_API_KEY + `$env:SAM_PORTAL_SERVICE_ID"
  Write-Host ""
  Write-Host "If auto-deploy is off (e.g. after Deploy a specific commit), use:"
  Write-Host "  Render -> sam-voice-portal -> Manual Deploy -> Deploy latest commit"
  exit 1
}

function PortalBuildLive {
  param([string]$Url)
  try {
    $html = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 25
    if ($html.Content -notmatch 'href="(/assets/index-[^"]+\.css)"') { return $false }
    $cssUrl = "$Url$($matches[1])"
    $css = (Invoke-WebRequest -Uri $cssUrl -UseBasicParsing -TimeoutSec 25).Content
    return $css -match 'portal-lockup'
  } catch {
    return $false
  }
}

function Wait-PortalLive {
  param([string]$Url, [int]$TimeoutSec)
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  $attempt = 0
  while ((Get-Date) -lt $deadline) {
    $attempt++
    if (PortalBuildLive -Url $Url) {
      Write-Host "[OK] Portal build live at $Url (portal-lockup present)" -ForegroundColor Green
      return $true
    }
    Write-Host "  waiting for portal deploy... attempt $attempt" -ForegroundColor DarkGray
    Start-Sleep -Seconds 20
  }
  Write-Host "[WARN] Portal wait timed out - deploy may still be building." -ForegroundColor Yellow
  return $false
}

Invoke-PortalDeploy

if ($Wait) {
  Write-Host "Waiting for portal at $PortalUrl ..." -ForegroundColor Cyan
  Wait-PortalLive -Url $PortalUrl -TimeoutSec $WaitTimeoutSec | Out-Null
} else {
  Write-Host "Tip: .\scripts\deploy-sam-portal-render.ps1 -Wait to block until the new portal build is live." -ForegroundColor DarkGray
}
