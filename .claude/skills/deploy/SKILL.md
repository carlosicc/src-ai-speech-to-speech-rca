---
name: deployment
description: Guides CDK deployment with pre/post checks
triggers:
  - "deploy"
  - "cdk deploy"
  - "push to production"
---

## Pre-deployment
1. Run `cdk diff` to review changes.
2. Verify no secrets in source code (`grep -r "AKIA\|sk-\|password" src_infra/`).
3. Run tests: `.venv/bin/pytest -v`.

## Deployment
1. `cdk deploy --all`

## Post-deployment
1. Deploy SSM parameters: `python src_config/scripts/deploy_ssm_parameters.py --env {env}`
2. Deploy secrets: `python src_config/scripts/deploy_secrets.py --env {env}`
3. Seed demo data: `python src_config/scripts/seed_demo_data.py --env {env}`
4. Verify ECS service: `aws ecs describe-services --cluster rca-backend-ecs-cluster-... --services rca-backend-ecs-agent-svc-...`
