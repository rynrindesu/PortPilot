<#
.SYNOPSIS
    Build and deploy the PortPilot console to S3 + CloudFront.

.EXAMPLE
    ./deploy/aws/deploy-frontend.ps1

.EXAMPLE
    # Point the deployed console at live backends instead of the demo dataset
    ./deploy/aws/deploy-frontend.ps1 -ReschedulingApi "https://api.example.com" -PortOpsApi "https://ops.example.com"
#>

[CmdletBinding()]
param(
    [string]$StackName = "portpilot-console",
    [string]$Region = "ap-southeast-1",
    [string]$ReschedulingApi = "",
    [string]$PortOpsApi = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$frontend = Join-Path $repoRoot "frontend"
$template = Join-Path $PSScriptRoot "frontend.yaml"

function Assert-LastExit($what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed with exit code $LASTEXITCODE" }
}

Write-Host ""
Write-Host "PortPilot console -> AWS" -ForegroundColor Cyan
Write-Host "  stack   $StackName"
Write-Host "  region  $Region"
Write-Host ""

# --- 0. preflight -------------------------------------------------------
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI not found. Install it, then run 'aws configure'. See deploy/aws/README.md."
}
$who = aws sts get-caller-identity --query Arn --output text 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "No usable AWS credentials. Run 'aws configure' first. See deploy/aws/README.md."
}
Write-Host "Authenticated as $who" -ForegroundColor DarkGray

# --- 1. build -----------------------------------------------------------
if (-not $SkipBuild) {
    Push-Location $frontend
    try {
        if (-not (Test-Path "node_modules")) {
            Write-Host "Installing dependencies..." -ForegroundColor Yellow
            npm install
            Assert-LastExit "npm install"
        }

        # Vite reads these at build time and bakes them into the bundle.
        if ($ReschedulingApi) { $env:VITE_RESCHEDULING_API = $ReschedulingApi }
        if ($PortOpsApi) { $env:VITE_PORT_OPS_API = $PortOpsApi }

        Write-Host "Building..." -ForegroundColor Yellow
        npm run build
        Assert-LastExit "vite build"
    }
    finally {
        Remove-Item Env:\VITE_RESCHEDULING_API -ErrorAction SilentlyContinue
        Remove-Item Env:\VITE_PORT_OPS_API -ErrorAction SilentlyContinue
        Pop-Location
    }
}

$dist = Join-Path $frontend "dist"
if (-not (Test-Path (Join-Path $dist "index.html"))) {
    throw "No build output at $dist. Run without -SkipBuild."
}

# --- 2. infrastructure --------------------------------------------------
Write-Host "Deploying CloudFormation stack..." -ForegroundColor Yellow
aws cloudformation deploy `
    --template-file $template `
    --stack-name $StackName `
    --region $Region `
    --no-fail-on-empty-changeset
Assert-LastExit "cloudformation deploy"

function Get-StackOutput($key) {
    $value = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue" `
        --output text
    Assert-LastExit "describe-stacks ($key)"
    return $value.Trim()
}

$bucket = Get-StackOutput "BucketName"
$distributionId = Get-StackOutput "DistributionId"
$url = Get-StackOutput "ConsoleUrl"

# --- 3. upload ----------------------------------------------------------
# Fingerprinted assets are immutable; the HTML entry point must never be.
Write-Host "Uploading fingerprinted assets..." -ForegroundColor Yellow
aws s3 sync $dist "s3://$bucket" `
    --region $Region `
    --delete `
    --exclude "*.html" `
    --cache-control "public,max-age=31536000,immutable"
Assert-LastExit "s3 sync (assets)"

Write-Host "Uploading entry point..." -ForegroundColor Yellow
aws s3 sync $dist "s3://$bucket" `
    --region $Region `
    --exclude "*" `
    --include "*.html" `
    --cache-control "no-cache,must-revalidate" `
    --content-type "text/html; charset=utf-8"
Assert-LastExit "s3 sync (html)"

# --- 4. invalidate ------------------------------------------------------
Write-Host "Invalidating CloudFront cache..." -ForegroundColor Yellow
$invalidationId = aws cloudfront create-invalidation `
    --distribution-id $distributionId `
    --paths "/*" `
    --query "Invalidation.Id" `
    --output text
Assert-LastExit "create-invalidation"

Write-Host ""
Write-Host "Deployed." -ForegroundColor Green
Write-Host "  $url" -ForegroundColor Cyan
Write-Host ""
Write-Host "  bucket        $bucket"
Write-Host "  distribution  $distributionId"
Write-Host "  invalidation  $invalidationId  (edge propagation takes 1-3 minutes)"
Write-Host ""
