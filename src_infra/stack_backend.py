from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput, Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
    aws_ecr_assets as ecr_assets,
)


class BackendStack(Stack):
    """ECS Fargate stack — hosts the agent backend and WebSocket server."""

    def __init__(self, scope: Construct, construct_id: str,
                 env_name: str, env_context: dict,
                 infrastructure, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_name = env_context.get("project_name", "rca")
        ecs_config = env_context.get("ecs", {})
        bedrock_config = env_context.get("bedrock", {})

        # VPC
        self.vpc = ec2.Vpc(
            self, f"Vpc-{env_name}",
            vpc_name=f"{project_name}-backend-vpc-{env_name}",
            max_azs=2,
            nat_gateways=1,
        )

        # ECS Cluster
        self.cluster = ecs.Cluster(
            self, f"Cluster-{env_name}",
            cluster_name=f"{project_name}-backend-ecs-cluster-{env_name}",
            vpc=self.vpc,
        )

        # Task execution role
        execution_role = iam.Role(
            self, f"TaskExecRole-{env_name}",
            role_name=f"{project_name}-backend-iam-ecs-exec-{env_name}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        # Task role (permissions for the running container)
        task_role = iam.Role(
            self, f"TaskRole-{env_name}",
            role_name=f"{project_name}-backend-iam-ecs-task-{env_name}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # Grant task role access to shared resources
        infrastructure.main_table.grant_read_write_data(task_role)
        infrastructure.raw_data_bucket.grant_read_write(task_role)

        # Bedrock invoke permission
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[f"arn:aws:bedrock:{bedrock_config.get('region', 'eu-west-1')}::foundation-model/*"],
            )
        )

        # Fargate Task Definition (placeholder — will be fully configured when backend code exists)
        self.task_definition = ecs.FargateTaskDefinition(
            self, f"TaskDef-{env_name}",
            family=f"{project_name}-backend-task-{env_name}",
            cpu=ecs_config.get("cpu", 512),
            memory_limit_mib=ecs_config.get("memory_mib", 1024),
            execution_role=execution_role,
            task_role=task_role,
        )

        # Outputs
        CfnOutput(self, "ClusterName", value=self.cluster.cluster_name)
        CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
