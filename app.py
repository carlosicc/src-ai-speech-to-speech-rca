#!/usr/bin/env python3
import json
import os
from pathlib import Path

import aws_cdk as cdk

from src_infra.stack_infrastructure import InfrastructureStack
from src_infra.stack_backend import BackendStack
from src_infra.stack_frontend import FrontendStack
from src_infra.stack_agentcore import AgentCoreStack


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


app = cdk.App()

# Read environment from context (default: dev01)
env_name = app.node.try_get_context("env") or "dev01"
env_context = app.node.try_get_context(env_name)

if not env_context:
    raise ValueError(f"No context found for environment: {env_name}")

# Merge local overrides (gitignored) on top of cdk.json context
local_context_path = Path(__file__).parent / "cdk.context.local.json"
if local_context_path.exists():
    local_data = json.loads(local_context_path.read_text())
    local_env = local_data.get(env_name, {})
    if local_env:
        env_context = deep_merge(env_context, local_env)

# AWS environment
aws_env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=env_context.get("region", "eu-west-1"),
)

# Common props passed to all stacks
common_props = {
    "env_name": env_name,
    "env_context": env_context,
    "env": aws_env,
}

# 1. Foundation stack (DynamoDB, S3, Lambda Layer)
stack_infrastructure = InfrastructureStack(
    app, f"RcaInfrastructureStack-{env_name}", **common_props
)

# 2. Backend stack (ECS Fargate — agents, WebSocket)
stack_backend = BackendStack(
    app, f"RcaBackendStack-{env_name}",
    infrastructure=stack_infrastructure,
    **common_props,
)
stack_backend.add_dependency(stack_infrastructure)

# 3. AgentCore stack (BidiAgent voice agent runtime)
stack_agentcore = AgentCoreStack(
    app, f"RcaAgentCoreStack-{env_name}",
    infrastructure=stack_infrastructure,
    **common_props,
)
stack_agentcore.add_dependency(stack_infrastructure)

# 4. Frontend stack (S3 + CloudFront)
stack_frontend = FrontendStack(
    app, f"RcaFrontendStack-{env_name}", **common_props
)

app.synth()
