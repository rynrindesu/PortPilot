<#
.SYNOPSIS
    Deploy the live-data console: two FastAPI services on EC2, fronted by their
    own CloudFront distribution, reading the real database and OCEANS-X feed.

.DESCRIPTION
    This is a SECOND deployment. It does not touch the demo console
    (stack "portpilot-console"), which keeps serving the bundled dataset.

    The API is exposed read-only by default: CloudFront allows only
    GET/HEAD/OPTIONS on /api/*, so a public audience can watch live data
    without being able to start a monitoring cycle - minutes of LLM calls per
    press - or upload documents.

    Run put-secrets.ps1 first: the instance reads its configuration from SSM
    Parameter Store and nothing is baked into the image or the template.

.EXAMPLE
    ./deploy/aws/put-secrets.ps1
    ./deploy/aws/deploy-live.ps1
#>

[CmdletBinding()]
param(
    [string]$BackendStack = "portpilot-api",
    [string]$ConsoleStack = "portpilot-console-live",
    [string]$Region = "ap-southeast-1",
    [string]$RepoUrl = "https://github.com/rynrindesu/PortPilot.git",
    [string]$RepoBranch = "live-data",
    # t3.micro is Free Tier but has 1 GB of RAM; langchain, langgraph and
    # pymupdf across two services fit far more comfortably in 2 GB.
    [ValidateSet("t3.micro", "t3.small", "t3.medium")]
    [string]$InstanceType = "t3.small",
    [switch]$AllowWrites,
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$frontend = Join-Path $repoRoot "frontend"

function Assert-LastExit($what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed with exit code $LASTEXITCODE" }
}

function Get-StackOutput($stack, $key) {
    $value = aws cloudformation describe-stacks `
        --stack-name $stack --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue" --output text
    Assert-LastExit "describe-stacks $stack/$key"
    return $value.Trim()
}

Write-Host ""
Write-Host "PortPilot live deployment" -ForegroundColor Cyan
Write-Host "  backend stack  $BackendStack"
Write-Host "  console stack  $ConsoleStack"
Write-Host "  branch         $RepoBranch"
Write-Host "  api writes     $(if ($AllowWrites) { 'ENABLED' } else { 'read-only' })"
Write-Host ""

# --- 0. preflight -------------------------------------------------------
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI not found. See deploy/aws/README.md."
}
$who = aws sts get-caller-identity --query Arn --output text 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "AWS credentials are missing or expired. Refresh them, then re-run. See deploy/aws/README.md."
}
Write-Host "Authenticated as $who" -ForegroundColor DarkGray

$configured = aws ssm get-parameters-by-path --path "/portpilot" --region $Region `
    --query "length(Parameters)" --output text 2>$null
if ($LASTEXITCODE -ne 0 -or [int]$configured -eq 0) {
    throw "No configuration found under /portpilot in SSM. Run ./deploy/aws/put-secrets.ps1 first."
}
Write-Host "Found $configured configuration parameters in SSM" -ForegroundColor DarkGray

# --- 1. backend ---------------------------------------------------------
if (-not $SkipBackend) {
    Write-Host "`nResolving default VPC and a public subnet..." -ForegroundColor Yellow
    $vpcId = aws ec2 describe-vpcs --region $Region `
        --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text
    Assert-LastExit "describe-vpcs"
    if (-not $vpcId -or $vpcId -eq "None") { throw "No default VPC in $Region." }

    $subnetId = aws ec2 describe-subnets --region $Region `
        --filters Name=vpc-id,Values=$vpcId Name=default-for-az,Values=true `
        --query "Subnets[0].SubnetId" --output text
    Assert-LastExit "describe-subnets"
    if (-not $subnetId -or $subnetId -eq "None") { throw "No default subnet in $vpcId." }

    # Restrict port 80 to CloudFront's edge servers where the managed prefix
    # list is available; fall back to open HTTP rather than failing the deploy.
    $prefixList = aws ec2 describe-managed-prefix-lists --region $Region `
        --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing `
        --query "PrefixLists[0].PrefixListId" --output text 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $prefixList -or $prefixList -eq "None") {
        $prefixList = ""
        Write-Host "  CloudFront prefix list unavailable; port 80 will be open." -ForegroundColor DarkYellow
    }

    Write-Host "  vpc $vpcId / subnet $subnetId$(if ($prefixList) { " / prefix list $prefixList" })" -ForegroundColor DarkGray

    Write-Host "`nDeploying backend stack (2-4 minutes to bootstrap)..." -ForegroundColor Yellow
    aws cloudformation deploy `
        --template-file (Join-Path $PSScriptRoot "backend-ec2.yaml") `
        --stack-name $BackendStack `
        --region $Region `
        --capabilities CAPABILITY_IAM `
        --no-fail-on-empty-changeset `
        --parameter-overrides `
            VpcId=$vpcId `
            SubnetId=$subnetId `
            InstanceType=$InstanceType `
            RepoUrl=$RepoUrl `
            RepoBranch=$RepoBranch `
            AllowedIngressPrefixListId=$prefixList
    Assert-LastExit "cloudformation deploy ($BackendStack)"
}

$apiDomain = Get-StackOutput $BackendStack "ApiOriginDomain"
$instanceId = Get-StackOutput $BackendStack "InstanceId"
Write-Host "`nBackend host: $apiDomain ($instanceId)" -ForegroundColor Green

# --- 2. wait for the services to answer ---------------------------------
Write-Host "Waiting for the services to come up..." -ForegroundColor Yellow
$healthy = $false
foreach ($attempt in 1..40) {
    try {
        $response = Invoke-WebRequest -Uri "http://$apiDomain/healthz" -TimeoutSec 5 -UseBasicParsing
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 15
    if ($attempt % 4 -eq 0) { Write-Host "  still bootstrapping ($($attempt * 15)s)..." -ForegroundColor DarkGray }
}

if (-not $healthy) {
    Write-Host "`nThe host did not answer /healthz in 10 minutes." -ForegroundColor Red
    Write-Host "Read the bootstrap log with:" -ForegroundColor Red
    Write-Host "  aws ssm start-session --target $instanceId --region $Region"
    Write-Host "  sudo tail -100 /var/log/portpilot-bootstrap.log"
    throw "backend not healthy"
}
Write-Host "  services responding" -ForegroundColor Green

# --- 3. console -----------------------------------------------------------
Write-Host "`nDeploying the live console distribution..." -ForegroundColor Yellow
aws cloudformation deploy `
    --template-file (Join-Path $PSScriptRoot "frontend.yaml") `
    --stack-name $ConsoleStack `
    --region $Region `
    --no-fail-on-empty-changeset `
    --parameter-overrides `
        ProjectName=portpilot-live `
        ApiOriginDomain=$apiDomain `
        ApiAllowWrites=$(if ($AllowWrites) { "true" } else { "false" })
Assert-LastExit "cloudformation deploy ($ConsoleStack)"

$bucket = Get-StackOutput $ConsoleStack "BucketName"
$distributionId = Get-StackOutput $ConsoleStack "DistributionId"
$url = Get-StackOutput $ConsoleStack "ConsoleUrl"

# --- 4. build against the same origin -------------------------------------
Push-Location $frontend
try {
    if (-not (Test-Path "node_modules")) { npm install; Assert-LastExit "npm install" }

    # Relative bases: the API is served from this distribution under /api/*,
    # so the browser sees one origin - no CORS, no mixed content.
    $env:VITE_RESCHEDULING_API = "/api/scheduling"
    $env:VITE_PORT_OPS_API = "/api/portops"
    $env:VITE_API_READ_ONLY = $(if ($AllowWrites) { "false" } else { "true" })

    Write-Host "Building the console against the live API..." -ForegroundColor Yellow
    npm run build
    Assert-LastExit "vite build"
}
finally {
    Remove-Item Env:\VITE_RESCHEDULING_API, Env:\VITE_PORT_OPS_API, Env:\VITE_API_READ_ONLY -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host "Uploading..." -ForegroundColor Yellow
aws s3 sync (Join-Path $frontend "dist") "s3://$bucket" --region $Region --delete `
    --exclude "*.html" --cache-control "public,max-age=31536000,immutable"
Assert-LastExit "s3 sync (assets)"

aws s3 sync (Join-Path $frontend "dist") "s3://$bucket" --region $Region `
    --exclude "*" --include "*.html" `
    --cache-control "no-cache,must-revalidate" --content-type "text/html; charset=utf-8"
Assert-LastExit "s3 sync (html)"

aws cloudfront create-invalidation --distribution-id $distributionId --paths "/*" `
    --query "Invalidation.Id" --output text | Out-Null
Assert-LastExit "create-invalidation"

Write-Host ""
Write-Host "Live console deployed." -ForegroundColor Green
Write-Host "  $url" -ForegroundColor Cyan
Write-Host ""
Write-Host "  backend host   $apiDomain"
Write-Host "  instance       $instanceId"
Write-Host "  api sample     $url/api/scheduling/vessels"
Write-Host ""
Write-Host "  The demo console is untouched and still serves the bundled dataset." -ForegroundColor DarkGray
Write-Host "  Tear both down with ./deploy/aws/teardown.ps1 when judging is over." -ForegroundColor DarkGray
Write-Host ""
