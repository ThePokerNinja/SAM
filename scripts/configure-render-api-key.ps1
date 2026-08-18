param()

$ErrorActionPreference = "Stop"

$secure = Read-Host "Paste the Render API key (input is hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if (-not $apiKey) {
    throw "No Render API key was entered."
}

$headers = @{
    Authorization = "Bearer $apiKey"
    Accept = "application/json"
}

try {
    $null = Invoke-RestMethod `
        -Method GET `
        -Uri "https://api.render.com/v1/owners?limit=1" `
        -Headers $headers `
        -TimeoutSec 30
} catch {
    $response = $_.Exception.Response
    if (-not $response) {
        throw "No HTTP response - request never reached Render: $($_.Exception.Message)"
    }
    $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
    throw "Render rejected the key with HTTP $([int]$response.StatusCode): $($reader.ReadToEnd())"
}

[Environment]::SetEnvironmentVariable("RENDER_API_KEY", $apiKey, "User")
$env:RENDER_API_KEY = $apiKey
Write-Host "Render API key validated and saved for this Windows user." -ForegroundColor Green
