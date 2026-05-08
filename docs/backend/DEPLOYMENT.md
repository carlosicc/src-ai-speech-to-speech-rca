# Deployment Guide

## Prerequisites
- AWS CDK CLI installed (`npm install -g aws-cdk`)
- AWS credentials configured for target account
- Python 3.12 with `.venv` activated
- Twilio account with phone number

## First-Time Setup

```bash
# Bootstrap CDK (once per account/region)
cdk bootstrap aws://ACCOUNT_ID/eu-west-1

# Deploy all stacks
cdk deploy --all -c env=dev01

# Configure external services
python src_config/scripts/deploy_ssm_parameters.py --env dev01
python src_config/scripts/deploy_secrets.py --env dev01
python src_config/scripts/seed_demo_data.py --env dev01
```

## Updating

```bash
# Preview changes
cdk diff --all -c env=dev01

# Deploy
cdk deploy --all -c env=dev01
```

## Stacks

| Stack | Resources |
|-------|-----------|
| RcaInfrastructureStack | DynamoDB table, S3 bucket, Lambda Layer |
| RcaBackendStack | VPC, ECS Cluster, Fargate Service |
| RcaFrontendStack | S3 + CloudFront (pending confirmation) |
