<#
.SYNOPSIS
    Store PortPilot backend configuration in SSM Parameter Store.

.DESCRIPTION
    Only needed if you deploy backend-ec2.yaml. Secrets are prompted for, never
    passed on the command line (which would land them in your shell history),
    and are written as SecureString parameters encrypted with the account's
    default SSM KMS key. The instance role can read only this prefix.

    Re-run it any time to rotate a value.

.EXAMPLE
    ./deploy/aws/put-secrets.ps1
#>

[CmdletBinding()]
param(
    [string]$Region = "ap-southeast-1",
    [string]$Prefix = "/portpilot"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI not found. See deploy/aws/README.md."
}

function Set-PlainParam {
    param([string]$Name, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return }
    aws ssm put-parameter `
        --name "$Prefix/$Name" `
        --value $Value `
        --type String `
        --overwrite `
        --region $Region | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "put-parameter $Name failed" }
    Write-Host "  set $Prefix/$Name = $Value" -ForegroundColor DarkGray
}

function Set-SecretParam {
    param([string]$Name, [string]$Prompt)
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }

    if ([string]::IsNullOrWhiteSpace($plain)) {
        Write-Host "  skipped $Name (blank)" -ForegroundColor DarkGray
        return
    }

    aws ssm put-parameter `
        --name "$Prefix/$Name" `
        --value $plain `
        --type SecureString `
        --overwrite `
        --region $Region | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $plain = $null
    [GC]::Collect()
    if (-not $ok) { throw "put-parameter $Name failed" }
    Write-Host "  set $Prefix/$Name = ********" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "PortPilot configuration -> SSM Parameter Store ($Prefix, $Region)" -ForegroundColor Cyan
Write-Host "Press Enter to skip any value you do not use." -ForegroundColor DarkGray
Write-Host ""

# --- non-secret ---------------------------------------------------------
$provider = Read-Host "LLM_PROVIDER (groq | bedrock | openai) [groq]"
if ([string]::IsNullOrWhiteSpace($provider)) { $provider = "groq" }
Set-PlainParam -Name "LLM_PROVIDER" -Value $provider
Set-PlainParam -Name "AWS_DEFAULT_REGION" -Value $Region
Set-PlainParam -Name "PORTPILOT_AUTOMATION_ENABLED" -Value "true"

$groqModel = Read-Host "GROQ_MODEL (blank to leave unset)"
Set-PlainParam -Name "GROQ_MODEL" -Value $groqModel

# --- secret -------------------------------------------------------------
Set-SecretParam -Name "SUPABASE_DB_URL" -Prompt "SUPABASE_DB_URL"
Set-SecretParam -Name "SUPABASE_DB_PASSWORD" -Prompt "SUPABASE_DB_PASSWORD"
Set-SecretParam -Name "OCEANX_VESSELS_DUE_TO_ARRIVE_API_KEY" -Prompt "OCEANX_VESSELS_DUE_TO_ARRIVE_API_KEY"
Set-SecretParam -Name "GROQ_API_KEY" -Prompt "GROQ_API_KEY"
Set-SecretParam -Name "OPENAI_API_KEY" -Prompt "OPENAI_API_KEY"

Write-Host ""
Write-Host "Stored. The instance reloads these at boot; after a change run:" -ForegroundColor Green
Write-Host "  aws ssm start-session --target <instance-id>"
Write-Host "  sudo /usr/local/bin/portpilot-load-config $Prefix $Region"
Write-Host "  sudo systemctl restart portpilot-scheduling portpilot-portops"
Write-Host ""
