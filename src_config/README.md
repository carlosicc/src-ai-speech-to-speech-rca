# Configuration Management

This directory manages all external configuration for the RCA Agent Demo.

## Flows

### Secrets (Twilio credentials, API keys)
```
.env.template (tracked) → .env.{env} (gitignored) → deploy_secrets.py → AWS Secrets Manager
                                                                              ↓
                                                                      ECS reads at runtime
                                                                      via secret ARN env var
```

### SSM Parameters (model IDs, feature flags)
```
cdk.json context → CDK deployment → SSM Parameter Store
                                          ↓
                                  Lambda/ECS reads at runtime
                                  via rca_utils.config.get_parameter()
```

### Prompts & Souls (agent instructions, personality)
```
src_config/prompts/*.json → seed_demo_data.py → DynamoDB (PROMPT#type / LATEST)
                                                         (SOUL#agent / LATEST)
                                                              ↓
                                                      Agent reads at runtime
                                                      with in-memory caching
```

## Scripts

| Script | Purpose |
|--------|---------|
| `deploy_secrets.py` | Push .env values to Secrets Manager |
| `deploy_ssm_parameters.py` | Push SSM parameters from yaml |
| `seed_demo_data.py` | Seed DynamoDB with prompts, souls, demo incidents |

## Usage

```bash
# First-time setup
python src_config/scripts/deploy_ssm_parameters.py --env dev01
python src_config/scripts/deploy_secrets.py --env dev01
python src_config/scripts/seed_demo_data.py --env dev01
```
