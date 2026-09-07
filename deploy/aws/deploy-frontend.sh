#!/usr/bin/env bash
# Build and deploy the PortPilot console to S3 + CloudFront.
#
#   ./deploy/aws/deploy-frontend.sh
#   VITE_RESCHEDULING_API=https://api.example.com ./deploy/aws/deploy-frontend.sh
#
# Environment overrides: STACK_NAME, AWS_REGION, SKIP_BUILD=1

set -euo pipefail

STACK_NAME="${STACK_NAME:-portpilot-console}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
frontend="$repo_root/frontend"
template="$script_dir/frontend.yaml"

printf '\nPortPilot console -> AWS\n  stack   %s\n  region  %s\n\n' "$STACK_NAME" "$AWS_REGION"

# --- 0. preflight -------------------------------------------------------
command -v aws >/dev/null 2>&1 || {
  echo "AWS CLI not found. Install it, then run 'aws configure'. See deploy/aws/README.md." >&2
  exit 1
}
aws sts get-caller-identity --query Arn --output text >/dev/null 2>&1 || {
  echo "No usable AWS credentials. Run 'aws configure' first." >&2
  exit 1
}

# --- 1. build -----------------------------------------------------------
if [ "${SKIP_BUILD:-0}" != "1" ]; then
  cd "$frontend"
  [ -d node_modules ] || { echo "Installing dependencies..."; npm install; }
  echo "Building..."
  npm run build
fi

[ -f "$frontend/dist/index.html" ] || {
  echo "No build output at $frontend/dist." >&2
  exit 1
}

# --- 2. infrastructure --------------------------------------------------
echo "Deploying CloudFormation stack..."
aws cloudformation deploy \
  --template-file "$template" \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --no-fail-on-empty-changeset

stack_output() {
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

bucket="$(stack_output BucketName)"
distribution_id="$(stack_output DistributionId)"
url="$(stack_output ConsoleUrl)"

# --- 3. upload ----------------------------------------------------------
echo "Uploading fingerprinted assets..."
aws s3 sync "$frontend/dist" "s3://$bucket" \
  --region "$AWS_REGION" \
  --delete \
  --exclude "*.html" \
  --cache-control "public,max-age=31536000,immutable"

echo "Uploading entry point..."
aws s3 sync "$frontend/dist" "s3://$bucket" \
  --region "$AWS_REGION" \
  --exclude "*" \
  --include "*.html" \
  --cache-control "no-cache,must-revalidate" \
  --content-type "text/html; charset=utf-8"

# --- 4. invalidate ------------------------------------------------------
echo "Invalidating CloudFront cache..."
invalidation_id="$(aws cloudfront create-invalidation \
  --distribution-id "$distribution_id" \
  --paths "/*" \
  --query "Invalidation.Id" \
  --output text)"

printf '\nDeployed.\n  %s\n\n  bucket        %s\n  distribution  %s\n  invalidation  %s  (edge propagation takes 1-3 minutes)\n\n' \
  "$url" "$bucket" "$distribution_id" "$invalidation_id"
