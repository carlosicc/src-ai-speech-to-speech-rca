#!/usr/bin/env python3
import os

import aws_cdk as cdk

from src_infra.stack_infrastructure import InfrastructureStack
from src_infra.stack_backend import BackendStack
from src_infra.stack_frontend import FrontendStack

app = cdk.App()

# Read environment from context (default: dev01)
env_name = app.node.try_get_context("env") or "dev01"
env_context = app.node.try_get_context(env_name)

if not env_context:
    raise ValueError(f"No context found for environment: {env_name}")

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

# 3. Frontend stack (S3 + CloudFront — pending public access confirmation)
stack_frontend = FrontendStack(
    app, f"RcaFrontendStack-{env_name}", **common_props
)
stack_frontend.add_dependency(stack_backend)

app.synth()
