# Deployment Guide

## Prerequisites
- AWS CDK CLI installed (`npm install -g aws-cdk@latest`)
- AWS credentials configured for target account (000000000000)
- Python 3.12 with `.venv` activated
- Twilio account with phone number (for Mode A/B voice calls)
- Node.js 18+ (for frontend build)

## First-Time Setup

```bash
# Bootstrap CDK (once per account/region)
cdk bootstrap aws://000000000000/eu-west-1

# Deploy all stacks
npx --package=aws-cdk@latest cdk deploy --all

# Configure secrets (Twilio credentials)
python src_config/scripts/deploy_secrets.py --env dev01

# Optional: seed DynamoDB with prompts/souls
python src_config/scripts/seed_demo_data.py --env dev01
```

## Updating

```bash
# Build frontend (VITE_WS_URL baked from .env.production)
cd src_frontend/app && npm run build && cd ../..

# Copy frontend to backend static (same-origin serving from ECS)
cp -r src_frontend/app/dist/* src_backend/static/

# Preview changes
npx --package=aws-cdk@latest cdk diff --all

# Deploy backend (CDK builds Docker image automatically)
npx --package=aws-cdk@latest cdk deploy RcaBackendStack-dev01 --require-approval never

# Deploy frontend (S3 + CloudFront)
npx --package=aws-cdk@latest cdk deploy RcaFrontendStack-dev01 --require-approval never
```

**Important deployment order**: When removing cross-stack references, deploy the consumer stack (Frontend) before the producer stack (Backend) to avoid CloudFormation "export in use" errors. For normal updates, order does not matter since the stacks are independent.

## Stacks

| Stack | Resources | Status |
|-------|-----------|--------|
| `RcaInfrastructureStack-dev01` | DynamoDB table, S3 bucket, Lambda Layer | Deployed |
| `RcaBackendStack-dev01` | VPC, ECS Cluster, Fargate Service, NLB, IAM | Deployed |
| `RcaAgentCoreStack-dev01` | AgentCore IAM role, ECR image (ARM64) | Deployed |
| `RcaFrontendStack-dev01` | S3 + CloudFront (Basic Auth) | Deployed |

## Deployed Endpoints

| Endpoint | URL |
|----------|-----|
| Demo URL (CloudFront + Basic Auth) | `https://rca-demo.aienaws.com` (demo / REDACTED_PASSWORD) |
| WebSocket (NLB direct) | `wss://ws.rca-demo.aienaws.com/ws` |
| Health check | `https://rca-nlb-ws-pub-dev01-XXXXXXXXXXXXXXXX.elb.eu-west-1.amazonaws.com/health` |
| Twilio Media Stream | `wss://ws.rca-demo.aienaws.com/twilio/media-stream` |
| Twilio TwiML webhook | `https://ws.rca-demo.aienaws.com/twilio/outbound-call` |

### DNS Setup (managed in separate Route53 account for aienaws.com)

| Record | Type | Target |
|--------|------|--------|
| `rca-demo.aienaws.com` | CNAME | `XXXXXXXXXXXX.cloudfront.net` |
| `ws.rca-demo.aienaws.com` | CNAME | `rca-nlb-ws-pub-dev01-XXXXXXXXXXXXXXXX.elb.eu-west-1.amazonaws.com` |

### TLS Certificates

| Domain | ACM Region | ARN |
|--------|-----------|-----|
| `ws.rca-demo.aienaws.com` | eu-west-1 | `arn:aws:acm:eu-west-1:000000000000:certificate/00000000-0000-0000-0000-000000000001` |
| `rca-demo.aienaws.com` + `ws.rca-demo.aienaws.com` | us-east-1 | `arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000002` |

### Architecture Note

Frontend (CloudFront) and WebSocket (NLB) are on **separate domains**. CloudFront does NOT proxy WebSocket traffic. The frontend has `VITE_WS_URL` baked in at build time (`src_frontend/app/.env.production`). All backend endpoints require API token auth (`API_TOKEN` env var on ECS task).

## ECS Service Details

| Setting | Value |
|---------|-------|
| Cluster | `rca-backend-ecs-cluster-dev01` |
| Service | `rca-backend-ecs-agent-svc-dev01` |
| CPU/Memory | 512 / 1024 MiB |
| Platform | Linux/AMD64 |
| Desired count | 1 |
| Circuit breaker | Enabled (rollback on failure) |

## Environment Variables (ECS Task)

| Variable | Value | Source |
|----------|-------|--------|
| `BEDROCK_MODEL_ID` | `eu.anthropic.claude-sonnet-4-6` | cdk.json context |
| `BEDROCK_REGION` | `eu-west-1` | cdk.json context |
| `NOVA_SONIC_MODEL_ID` | `amazon.nova-sonic-v1:0` | hardcoded |
| `NOVA_SONIC_REGION` | `us-east-1` | hardcoded (only available region) |
| `VOICE_PASSPHRASE` | `REDACTED_PASSPHRASE` | cdk.json |
| `VOICE_SESSION_TIMEOUT` | `90` | seconds |
| `TWILIO_CALLING_TIMEOUT` | `45` | seconds |
| `INCIDENT_LOOP_INTERVAL` | `180` | seconds (auto-loop) |
| `DEFAULT_VOICE_MODE` | `mode_c` | fallback mode |
| `TWILIO_SECRET_ARN` | (from Secrets Manager) | CDK |
| `API_TOKEN` | `REDACTED_API_TOKEN` | cdk.json context |
| `AGENTCORE_RUNTIME_ARN` | (from cdk.json) | CDK |

## AgentCore Runtime

AgentCore is NOT CDK-managed (CFN resource validation fails). Hybrid approach:
- **CDK manages:** IAM role, ECR container image (ARM64)
- **API manages:** Runtime creation + endpoint

```bash
# Check runtime status
aws bedrock-agentcore get-agent-runtime \
  --agent-runtime-id rca_voice_agent_dev01-XXXXXXXXXX \
  --region eu-west-1

# Update runtime after code change
npx --package=aws-cdk@latest cdk deploy RcaAgentCoreStack-dev01
# Then update via MCP tool or AWS CLI with new image URI
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `exec format error` | Ensure `platform=Platform.LINUX_AMD64` in DockerImageAsset |
| Model ID invalid | Use `eu.anthropic.claude-sonnet-4-6` (inference profile, not raw model) |
| AccessDeniedException on bedrock | IAM needs `arn:aws:bedrock:*::foundation-model/*` + `arn:aws:bedrock:*:{account}:inference-profile/*` |
| Container stuck deploying | Check `circuit_breaker` rollback, inspect CloudWatch logs |
| Voice session hangs | Check VOICE_SESSION_TIMEOUT, verify Nova Sonic available in us-east-1 |
