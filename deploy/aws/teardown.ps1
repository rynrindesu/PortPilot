<#
.SYNOPSIS
    Remove the PortPilot AWS stacks and stop all charges.

.DESCRIPTION
    Empties the site bucket first - CloudFormation refuses to delete a bucket
    that still has objects in it - then deletes the stacks. CloudFront takes
    several minutes to disable and remove; that is normal.

.EXAMPLE
    ./deploy/aws/teardown.ps1
#>

[CmdletBinding()]
param(
    [string]$FrontendStack = "portpilot-console",
    [string]$LiveConsoleStack = "portpilot-console-live",
    [string]$BackendStack = "portpilot-api",
    [string]$Region = "ap-southeast-1",
    [switch]$KeepParameters
)

$ErrorActionPreference = "Stop"

function Test-Stack($name) {
    aws cloudformation describe-stacks --stack-name $name --region $Region 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

Write-Host ""
Write-Host "Tearing down PortPilot in $Region" -ForegroundColor Yellow
Write-Host ""

# --- backend ------------------------------------------------------------
if (Test-Stack $BackendStack) {
    Write-Host "Deleting $BackendStack..." -ForegroundColor Yellow
    aws cloudformation delete-stack --stack-name $BackendStack --region $Region
    aws cloudformation wait stack-delete-complete --stack-name $BackendStack --region $Region
    Write-Host "  gone" -ForegroundColor Green
}
else {
    Write-Host "$BackendStack not deployed - skipping" -ForegroundColor DarkGray
}

# --- live console -------------------------------------------------------
if (Test-Stack $LiveConsoleStack) {
    $liveBucket = aws cloudformation describe-stacks `
        --stack-name $LiveConsoleStack `
        --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" `
        --output text

    if ($liveBucket -and $liveBucket -ne "None") {
        Write-Host "Emptying s3://$($liveBucket.Trim())..." -ForegroundColor Yellow
        aws s3 rm "s3://$($liveBucket.Trim())" --recursive --region $Region | Out-Null
    }

    Write-Host "Deleting $LiveConsoleStack..." -ForegroundColor Yellow
    aws cloudformation delete-stack --stack-name $LiveConsoleStack --region $Region
    aws cloudformation wait stack-delete-complete --stack-name $LiveConsoleStack --region $Region
    Write-Host "  gone" -ForegroundColor Green
}
else {
    Write-Host "$LiveConsoleStack not deployed - skipping" -ForegroundColor DarkGray
}

# --- demo frontend ------------------------------------------------------
if (Test-Stack $FrontendStack) {
    $bucket = aws cloudformation describe-stacks `
        --stack-name $FrontendStack `
        --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" `
        --output text

    if ($bucket -and $bucket -ne "None") {
        Write-Host "Emptying s3://$($bucket.Trim())..." -ForegroundColor Yellow
        aws s3 rm "s3://$($bucket.Trim())" --recursive --region $Region | Out-Null
    }

    Write-Host "Deleting $FrontendStack (CloudFront removal takes a few minutes)..." -ForegroundColor Yellow
    aws cloudformation delete-stack --stack-name $FrontendStack --region $Region
    aws cloudformation wait stack-delete-complete --stack-name $FrontendStack --region $Region
    Write-Host "  gone" -ForegroundColor Green
}
else {
    Write-Host "$FrontendStack not deployed - skipping" -ForegroundColor DarkGray
}

# --- parameters ---------------------------------------------------------
if (-not $KeepParameters) {
    $names = aws ssm get-parameters-by-path `
        --path "/portpilot" `
        --recursive `
        --region $Region `
        --query "Parameters[].Name" `
        --output text 2>$null

    if ($LASTEXITCODE -eq 0 -and $names -and $names.Trim()) {
        $list = $names -split "\s+" | Where-Object { $_ }
        Write-Host "Deleting $($list.Count) SSM parameter(s)..." -ForegroundColor Yellow
        foreach ($n in $list) {
            aws ssm delete-parameter --name $n --region $Region 2>$null | Out-Null
        }
        Write-Host "  gone" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Teardown complete. Check the Billing console in ~24h to confirm nothing lingers." -ForegroundColor Green
Write-Host ""
