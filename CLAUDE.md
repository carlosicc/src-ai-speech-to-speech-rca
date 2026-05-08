# Development Standards & Conventions — RCA Agent Demo

This file contains **binding rules for Claude Code**. Rules override all default behaviors. Read and follow before taking any action.

**Project**: Alert to Action — AI Operations Center Demo  
**Event**: AWS Summit Milan 2026 (AI Village)  
**Last Updated**: 2026-05-08

---

## CRITICAL RULES (Non-Negotiable)

### Think Before Coding
- State assumptions explicitly before implementing. If uncertain, ask — don't guess.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### Simplicity First
- No features beyond what was asked. No abstractions for single-use code.
- No speculative "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- The test: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### Surgical Changes
- Touch only what you must. Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken. Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that YOUR changes made unused. Don't remove pre-existing dead code unless asked.
- The test: Every changed line should trace directly to the user's request.

### Goal-Driven Execution
- Transform tasks into verifiable goals with success criteria before implementing.
- "Add validation" → "Write tests for invalid inputs, then make them pass."
- "Fix the bug" → "Write a test that reproduces it, then make it pass."
- For multi-step tasks, state a brief plan with verification checkpoints.

### Autonomy & Confirmations
- Run commands without asking for confirmation — bash, file edits, cdk diff, pytest, npm.
- Only ask before: destructive/irreversible actions (rm -rf, git reset --hard, cdk destroy, force-push, dropping tables, deleting AWS resources).

---

## 1. AI / LLM Integration

- NEVER call LLM APIs (bedrock-runtime, OpenAI SDK, etc.) directly.
- Always use **Strands Agents SDK** for agent implementation.
- Model IDs are in `cdk.json` context. Read from CDK context or SSM — never hardcode.
- NEVER hardcode prompts in application code. Store in DynamoDB (`PROMPT#{agent_type}` / `LATEST`).
- Agent souls (personality, tone, values) stored in DynamoDB (`SOUL#{agent_name}` / `LATEST`).

### Agent Framework Pattern

```python
from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(
    model_id=os.environ["BEDROCK_MODEL_ID"],
    region_name=os.environ["BEDROCK_REGION"],
)

agent = Agent(
    name="diagnosis_agent",
    model=model,
    system_prompt=get_agent_prompt("diagnosis"),
    tools=[check_db_health, pull_logs, run_healthcheck],
)
response = agent(prompt=incident_description)
```

### Anti-Pattern

```python
# BAD — direct SDK call
import boto3
client = boto3.client("bedrock-runtime")
response = client.invoke_model(modelId="anthropic.claude-sonnet...", body=...)

# BAD — hardcoded prompt
SYSTEM_PROMPT = "You are a diagnosis agent that..."
```

---

## 2. Python Environment

- NEVER create a new virtual environment. Use the existing `.venv/` at project root.
- NEVER install packages globally. Always use `.venv/bin/pip install`.
- Run Python as `.venv/bin/python` or activate `.venv` first.
- Python version: 3.12 (pinned in `.python-version`).
- Type hints required on all function signatures.
- Use `logger.info()` / `logger.error()` — never `print()`.

---

## 3. Infrastructure & Deployment

- NEVER use AWS CLI to create, update, or delete resources. All infrastructure via CDK.
- Deploy with: `cdk deploy` (specific stack) or `cdk deploy --all`.
- CDK stacks are in `src_infra/`. One stack per logical service.
- Backend runs on **ECS Fargate** (persistent WebSocket, Nova Sonic streaming).
- Lambda functions use `PythonFunction` (aws_cdk.aws_lambda_python_alpha).
- All Lambdas include the `common_utils` layer.
- Environment variables set in CDK, read at runtime via `os.environ`.
- Secrets via Secrets Manager (ARN in env var), config via SSM Parameter Store.

### Stack Structure

| Stack | Purpose |
|-------|---------|
| `RcaInfrastructureStack` | DynamoDB, S3, Lambda Layer, Secrets |
| `RcaBackendStack` | ECS Fargate (agents, WebSocket server) |
| `RcaFrontendStack` | S3 + CloudFront (static React app) |

---

## 4. Naming Conventions

Pattern: `rca-{component}-{aws_svc}-{name}-{account_id}-{region}-{env_suffix}`

| Resource | Example |
|----------|---------|
| DynamoDB table | `rca-ddb-table-app-dev01` |
| S3 bucket | `rca-s3-raw-data-123456789012-eu-west-1-dev01` |
| ECS cluster | `rca-backend-ecs-cluster-123456789012-eu-west-1-dev01` |
| ECS service | `rca-backend-ecs-agent-svc-123456789012-eu-west-1-dev01` |
| Lambda function | `rca-agent-diagnosis-dev01` |
| Secrets Manager | `rca-secret-twilio-123456789012-eu-west-1-dev01` |
| CDK Stack | `RcaInfrastructureStack-dev01` |
| AgentCore | `rca_backend_ac_master_123456789012_eu_west_1_dev_01` |

**Rules:**
- Every resource gets an explicit name — never rely on auto-generated names.
- Hyphens everywhere except AgentCore (underscores required).
- Short-name resources (ALB/TG, 32 char limit): drop account_id and region.

---

## 5. Security — No Public Access by Default

- NEVER create any resource with public access unless the user explicitly confirms.
- S3 buckets: always `block_public_access=BlockPublicAccess.BLOCK_ALL`.
- Security groups: no inbound from `0.0.0.0/0` unless explicitly approved.
- ALBs: default `internal=True`. Public ALBs require user confirmation.
- Lambda function URLs: do not create. Use API Gateway with auth.
- API Gateway: require authentication (IAM, Cognito, API keys).
- CloudFront: inherently public — always ask user to confirm before creating.
- If in doubt, **stop and ask**.

---

## 6. DynamoDB — Single Table Design

- One table: `rca-ddb-table-app-{env}`
- Do not create additional tables.
- Use shared helpers from Lambda layer: `from rca_utils.dynamodb import get_item, put_item, query_items`

### Entity Key Patterns

| Entity | PK | SK |
|--------|----|----|
| Incident | `INCIDENT#{id}` | `METADATA` |
| Incident Phase | `INCIDENT#{id}` | `PHASE#{timestamp}` |
| Prompt | `PROMPT#{agent_type}` | `LATEST` |
| Prompt Version | `PROMPT#{agent_type}` | `v{n}` |
| Soul | `SOUL#{agent_name}` | `LATEST` |
| Config | `CONFIG#{name}` | `LATEST` |

---

## 7. Shared Code — Lambda Layer

- All shared code in `src_infra/lambda_layers/common_utils/python/rca_utils/`.
- Import as: `from rca_utils import config, dynamodb, s3, secrets`
- Never duplicate utilities inside individual Lambda directories.

---

## 8. Project Context

This is a **demo** for AWS Summit Milan 2026 (AI Village booth). The demo loop:
1. Dashboard shows healthy "city" (animated frontend)
2. Production database goes down
3. Master agent activates sub-agents (diagnosis, escalation)
4. AI places real phone call to on-call DBA via Nova Sonic + Twilio
5. DBA authenticates by voice passphrase
6. Agent executes recovery, city recovers

**Agents:**
- **Master Agent**: Orchestrates incident response, activates sub-agents based on SoP
- **Diagnosis Agent**: Pulls logs, runs health checks, produces RCA summary
- **Escalation Agent**: Sends WhatsApp alerts (non-prod) or triggers voice call (prod)
- **Voice Agent**: Places outbound call via Twilio, powered by Nova Sonic STS

**This is a demo, not production software.** Optimize for:
- Visual impact at a booth
- Reliability during a 3-minute demo loop
- Easy reset between demo runs

---

## 9. Testing

- Framework: pytest
- CDK stacks: use `aws_cdk.assertions.Template.from_stack()`
- Lambda functions: test with mock events and mocked boto3 clients
- Run with: `.venv/bin/pytest -v`
- Frontend: Vitest + React Testing Library

---

## 10. Configuration & Environment

### Config flows:
- **Secrets**: `.env.template` → `.env.{env}` (gitignored) → `deploy_secrets.py` → Secrets Manager → Lambda reads via ARN env var
- **SSM**: `cdk.json` context → CDK deploy → SSM → Lambda reads via `rca_utils.config.get_parameter()`
- **Prompts**: `src_config/prompts/*.json` → `seed_demo_data.py` → DynamoDB → Lambda reads with in-memory cache

### Deployment:
1. `cdk deploy --all`
2. `python src_config/scripts/deploy_ssm_parameters.py --env dev01`
3. `python src_config/scripts/deploy_secrets.py --env dev01`
4. `python src_config/scripts/seed_demo_data.py --env dev01`

---

## 11. Adding New Features Checklist

- [ ] Create Lambda dir: `src_infra/lambda_functions/{group}_{purpose}/`
- [ ] Handler: `{group}_{purpose}.py` with `lambda_handler(event, context)`
- [ ] Add `requirements.txt` if deps beyond layer
- [ ] CDK: `PythonFunction` with `layers=[infrastructure.common_layer]`
- [ ] Set env vars (table name, bucket, region, model ID, secret ARNs)
- [ ] Grant IAM permissions (least privilege)
- [ ] Logging: `logger.info()` / `logger.error()`
- [ ] Verify no public access on any resource
- [ ] Run `cdk diff`, then `cdk deploy`
