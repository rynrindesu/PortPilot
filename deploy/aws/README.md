# Deploying PortPilot on AWS

Two stacks, deployed independently.

```
                    ┌──────────────────────────────────────┐
   judges ────────► │  CloudFront (HTTPS, global)          │
                    ├──────────────────────────────────────┤
                    │  /*        →  S3 (private, OAC)      │  frontend.yaml
                    │  /api/*    →  EC2 : nginx : uvicorn  │  backend-ec2.yaml
                    └──────────────────────────────────────┘
                                        │
                                        ▼
                             Supabase Postgres, OCEANS-X,
                             Bedrock / Groq  (unchanged)
```

Both services sit behind the **same** CloudFront distribution. That is
deliberate: the browser only ever talks to one HTTPS origin, so there is no
CORS to configure, no mixed-content problem, and no TLS certificate or domain
needed on the instance.

## What it costs

| Stack | Resources | Cost |
| --- | --- | --- |
| `frontend.yaml` | S3 + CloudFront | **≈ $0.20** for a hackathon's traffic. CloudFront's perpetual free tier covers 1 TB/month out and 10 M requests. |
| `backend-ec2.yaml` | 1× t3.micro, 20 GB gp3, no NAT, no ALB, no Elastic IP | **$0** on a new account (Free Tier: 750 h/month for 12 months). Otherwise ≈ **$8.50/month**, ≈ $0.29/day. |

On a $20 budget: deploy the frontend and leave it up. Deploy the backend only
while you need it, and run `teardown.ps1` when you are done. There is no NAT
Gateway and no load balancer anywhere in this design — those are what usually
eat a hackathon budget.

---

## Step 1 — Install and configure the AWS CLI

Nothing AWS-related is installed on this machine yet. In **PowerShell**:

```powershell
winget install --exact --id Amazon.AWSCLI
```

Close and reopen PowerShell, then confirm:

```powershell
aws --version
```

Create an access key in the AWS Console — **IAM → Users → your user → Security
credentials → Create access key → Command Line Interface (CLI)** — then:

```powershell
aws configure
```

Answer with your access key ID, secret access key, `ap-southeast-1`, and
`json`. Verify:

```powershell
aws sts get-caller-identity
```

> Treat the secret access key like a password. It is written to
> `%USERPROFILE%\.aws\credentials` in plain text. Delete the key in IAM when
> the hackathon is over.

## Step 2 — Deploy the console

From the repository root:

```powershell
./deploy/aws/deploy-frontend.ps1
```

That builds `frontend/`, creates the stack, uploads `dist/` with correct cache
headers (fingerprinted assets immutable for a year, `index.html` never cached),
invalidates the CloudFront cache, and prints the URL:

```
https://d1234abcd.cloudfront.net
```

First deployment takes 3–6 minutes because CloudFront has to propagate.
Re-deployments after a code change take about 30 seconds:

```powershell
./deploy/aws/deploy-frontend.ps1
```

That URL is your demo link. The console runs on its bundled operating-day
dataset — no database, no API keys, nothing to break in front of judges.

---

## Step 3 (optional) — Deploy the backend services

Only do this if you want the console reading live data. It costs money and
needs your Supabase, OCEANS-X and LLM credentials in the cloud.

### 3a. Store the configuration

```powershell
./deploy/aws/put-secrets.ps1
```

Prompts for each value and writes it to SSM Parameter Store as a SecureString.
Nothing is passed on the command line, so nothing lands in your shell history.

### 3b. Launch the instance

Find your default VPC and a subnet:

```powershell
aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text
aws ec2 describe-subnets --filters Name=default-for-az,Values=true --query "Subnets[0].SubnetId" --output text
```

Optionally lock port 80 to CloudFront's edge servers only:

```powershell
aws ec2 describe-managed-prefix-lists --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing --query "PrefixLists[0].PrefixListId" --output text
```

Then:

```powershell
aws cloudformation deploy `
  --template-file deploy/aws/backend-ec2.yaml `
  --stack-name portpilot-api `
  --region ap-southeast-1 `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides VpcId=vpc-xxxx SubnetId=subnet-xxxx AllowedIngressPrefixListId=pl-xxxx
```

Bootstrap takes 2–4 minutes. Check it:

```powershell
aws cloudformation describe-stacks --stack-name portpilot-api --query "Stacks[0].Outputs" --output table
curl http://<ApiOriginDomain>/healthz
```

If a service does not come up, shell in without SSH and read the log:

```powershell
aws ssm start-session --target <InstanceId>
sudo tail -100 /var/log/portpilot-bootstrap.log
sudo systemctl status portpilot-scheduling portpilot-portops
```

### 3c. Point CloudFront at it, and rebuild the console

```powershell
aws cloudformation deploy `
  --template-file deploy/aws/frontend.yaml `
  --stack-name portpilot-console `
  --region ap-southeast-1 `
  --parameter-overrides ApiOriginDomain=<ApiOriginDomain>

./deploy/aws/deploy-frontend.ps1 -ReschedulingApi "/api/scheduling" -PortOpsApi "/api/portops"
```

The API paths are **relative** on purpose — same origin as the console, so the
browser needs no CORS grant and the instance needs no certificate.

> Stopping and starting the instance changes its public DNS name. Re-run 3c
> with the new `ApiOriginDomain` if you do that.

---

## Step 4 — Tear down

```powershell
./deploy/aws/teardown.ps1
```

Empties the bucket, deletes both stacks, removes the SSM parameters. Add
`-KeepParameters` to keep your credentials stored for next time.

---

## Security notes

- The S3 bucket is private. CloudFront reads it through Origin Access Control;
  there is no public bucket policy and no website endpoint.
- The instance has **no SSH port and no key pair**. Shell access is via SSM
  Session Manager, which is audited and needs no inbound rule.
- Secrets live in SSM Parameter Store as SecureStrings. The instance role can
  read only `/portpilot/*` and can only decrypt through SSM.
- `bedrock:InvokeModel` and the Textract actions are granted on `*` because
  neither service supports meaningful resource-level scoping for these calls.
  Drop that policy block entirely if you use Groq or OpenAI instead.
- Port 80 on the instance is plaintext, but it is only reachable from
  CloudFront when you pass `AllowedIngressPrefixListId`. Pass it.

## Files

| File | Purpose |
| --- | --- |
| `frontend.yaml` | S3 + CloudFront, with an optional `/api/*` behaviour |
| `backend-ec2.yaml` | EC2 + nginx + systemd units for both FastAPI services |
| `deploy-frontend.ps1` / `.sh` | Build, deploy, upload, invalidate |
| `put-secrets.ps1` | Write configuration to SSM Parameter Store |
| `teardown.ps1` | Delete everything |
