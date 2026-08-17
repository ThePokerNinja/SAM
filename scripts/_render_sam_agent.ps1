# Shared Render service id resolution for sam-agent scripts.

function Get-SamAgentServiceId {
    $serviceId = ($(if ($env:SAM_AGENT_SERVICE_ID) { $env:SAM_AGENT_SERVICE_ID } else { "" })).Trim()
    if ($serviceId) { return $serviceId }
    $hook = ($(if ($env:SAM_AGENT_DEPLOY_HOOK_URL) {
        $env:SAM_AGENT_DEPLOY_HOOK_URL
    } elseif ($env:RENDER_DEPLOY_HOOK_URL) {
        $env:RENDER_DEPLOY_HOOK_URL
    } else {
        ""
    })).Trim()
    if ($hook -match '/deploy/(srv-[a-z0-9]+)') {
        return $Matches[1]
    }
    return ""
}

function Get-RenderApiKey {
    return ($(if ($env:RENDER_API_KEY) { $env:RENDER_API_KEY } else { "" })).Trim()
}

function Invoke-RenderGet {
    param(
        [string]$Uri,
        [hashtable]$Headers
    )
    try {
        return Invoke-RestMethod -Method GET -Uri $Uri -Headers $Headers -TimeoutSec 60
    } catch {
        $resp = $_.Exception.Response
        if (-not $resp) {
            throw "No HTTP response - request never reached Render: $($_.Exception.Message)"
        }
        $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $body = $sr.ReadToEnd()
        throw "Render GET $Uri failed HTTP $([int]$resp.StatusCode): $body"
    }
}

function Get-SamAgentLatestDeploy {
    param(
        [string]$ServiceId,
        [hashtable]$Headers
    )
    $rows = Invoke-RenderGet `
        -Uri "https://api.render.com/v1/services/$ServiceId/deploys?limit=1" `
        -Headers $Headers
    if (-not $rows -or $rows.Count -lt 1) {
        throw "No deploy rows returned for service $ServiceId"
    }
    $row = $rows[0]
    if ($row.deploy) { return $row.deploy }
    return $row
}

function Assert-SamAgentRenderCredentials {
    $apiKey = Get-RenderApiKey
    $serviceId = Get-SamAgentServiceId
    if (-not $apiKey) {
        throw "RENDER_API_KEY is required (Render -> Account Settings -> API Keys)"
    }
    if (-not $serviceId) {
        throw "SAM_AGENT_SERVICE_ID is required, or set SAM_AGENT_DEPLOY_HOOK_URL containing srv-..."
    }
    return @{
        ApiKey    = $apiKey
        ServiceId = $serviceId
        Headers   = @{
            Authorization  = "Bearer $apiKey"
            Accept         = "application/json"
            "Content-Type" = "application/json"
        }
    }
}
