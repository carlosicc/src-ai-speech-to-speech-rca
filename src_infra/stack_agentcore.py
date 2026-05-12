"""CDK Stack for AgentCore Runtime — builds container image and IAM role.

The AgentCore Runtime itself is created via the AgentCore API (not CFN)
because the CFN resource type doesn't support all required properties.
The CDK stack manages: ECR image asset, IAM execution role, permissions.
"""

import os

from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
)


class AgentCoreStack(Stack):
    """AgentCore supporting resources: container image + IAM role."""

    def __init__(self, scope: Construct, construct_id: str,
                 env_name: str, env_context: dict,
                 infrastructure, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_name = env_context.get("project_name", "rca")

        # Docker image for the BidiAgent container
        agent_image = ecr_assets.DockerImageAsset(
            self, f"AgentCoreImage-{env_name}",
            directory=os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "src_backend", "voice", "agentcore_agent",
            ),
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        # IAM role for the AgentCore Runtime
        runtime_role = iam.Role(
            self, f"AgentCoreRole-{env_name}",
            role_name=f"{project_name}-agentcore-role-{env_name}",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            ),
        )

        # Grant Bedrock Nova Sonic invocation
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:InvokeModelWithBidirectionalStream",
                ],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-sonic-v1:0",
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-2-sonic-v1:0",
                ],
            )
        )

        # Grant ECR pull for the container image
        agent_image.repository.grant_pull(runtime_role)

        # Grant CloudWatch logs
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        # Store for reference
        self.runtime_role = runtime_role
        self.image_uri = agent_image.image_uri
        self.runtime_arn = ""  # Set after API creation

        # Outputs
        CfnOutput(self, "AgentCoreImageUri", value=agent_image.image_uri)
        CfnOutput(self, "AgentCoreRoleArn", value=runtime_role.role_arn)
        CfnOutput(self, "AgentCoreRoleName", value=runtime_role.role_name)
