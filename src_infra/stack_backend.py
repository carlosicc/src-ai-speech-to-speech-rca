import os

from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput, Duration, RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
    aws_ecr_assets as ecr_assets,
    aws_elasticloadbalancingv2 as elbv2,
    aws_rds as rds,
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

        # Twilio secret (account_sid, auth_token, from_number as JSON)
        twilio_config = env_context.get("twilio", {})
        twilio_secret_arn = twilio_config.get("secret_arn", "") or self.node.try_get_context("twilio_secret_arn") or ""
        if twilio_secret_arn:
            from aws_cdk import aws_secretsmanager as secretsmanager
            twilio_secret = secretsmanager.Secret.from_secret_complete_arn(
                self, f"TwilioSecret-{env_name}", twilio_secret_arn
            )
            twilio_secret.grant_read(task_role)
        else:
            task_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[f"arn:aws:secretsmanager:*:{self.account}:secret:rca-secret-twilio-*"],
                )
            )

        # Bedrock invoke permission — cross-region inference profiles route to multiple regions
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:InvokeModelWithBidirectionalStream",
                ],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
                ],
            )
        )

        # --- Aurora MySQL Serverless v2 (demo database) ---

        # Security group for Aurora — allows 3306 only from ECS service SG
        self.rds_sg = ec2.SecurityGroup(
            self, f"RdsSg-{env_name}",
            security_group_name=f"{project_name}-backend-sg-rds-{env_name}",
            vpc=self.vpc,
            allow_all_outbound=False,
            description="Aurora MySQL - inbound 3306 from ECS tasks only",
        )

        # Aurora cluster with auto-generated credentials in Secrets Manager
        self.aurora_cluster = rds.DatabaseCluster(
            self, f"AuroraCluster-{env_name}",
            cluster_identifier=f"{project_name}-rds-aurora-cluster-{env_name}",
            engine=rds.DatabaseClusterEngine.aurora_mysql(
                version=rds.AuroraMysqlEngineVersion.VER_3_08_0,
            ),
            credentials=rds.Credentials.from_generated_secret(
                username="admin",
                secret_name=f"{project_name}-secret-rds-admin-{self.account}-{self.region}-{env_name}",
            ),
            default_database_name="operations",
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=1,
            writer=rds.ClusterInstance.serverless_v2(
                "WriterInstance",
                instance_identifier=f"{project_name}-rds-aurora-writer-{env_name}",
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.rds_sg],
            storage_encrypted=True,
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
        )

        # Grant ECS task role RDS control-plane operations
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "rds:DescribeDBClusters",
                    "rds:DescribeDBInstances",
                    "rds:StopDBCluster",
                    "rds:StartDBCluster",
                ],
                resources=[
                    f"arn:aws:rds:{self.region}:{self.account}:cluster:{project_name}-rds-aurora-cluster-{env_name}",
                    f"arn:aws:rds:{self.region}:{self.account}:db:{project_name}-rds-aurora-writer-{env_name}",
                ],
            )
        )

        # Grant ECS task role CloudWatch read access (Phase 2 — real metrics)
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:GetMetricData",
                ],
                resources=["*"],
            )
        )

        # Phase 3 — CloudWatch Logs Insights + RDS events for diagnosis agent tools
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:StartQuery",
                    "logs:GetQueryResults",
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/rds/cluster/{project_name}-rds-aurora-cluster-{env_name}/*",
                ],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["rds:DescribeEvents"],
                resources=["*"],
            )
        )

        # Grant ECS task role read access to the RDS secret
        self.aurora_cluster.secret.grant_read(task_role)

        # Docker image from src_backend/
        backend_image = ecr_assets.DockerImageAsset(
            self, f"BackendImage-{env_name}",
            directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "src_backend"),
            platform=ecr_assets.Platform.LINUX_AMD64,
        )

        # Log group
        log_group = logs.LogGroup(
            self, f"LogGroup-{env_name}",
            log_group_name=f"/ecs/{project_name}-backend-ecs-agent-svc-{env_name}",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # Fargate Task Definition
        self.task_definition = ecs.FargateTaskDefinition(
            self, f"TaskDef-{env_name}",
            family=f"{project_name}-backend-task-{env_name}",
            cpu=ecs_config.get("cpu", 512),
            memory_limit_mib=ecs_config.get("memory_mib", 1024),
            execution_role=execution_role,
            task_role=task_role,
        )

        # Container
        container = self.task_definition.add_container(
            f"AgentContainer-{env_name}",
            container_name=f"{project_name}-backend-agent",
            image=ecs.ContainerImage.from_docker_image_asset(backend_image),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="agent",
                log_group=log_group,
            ),
            environment={
                "WS_PORT": "8080",
                "INCIDENT_LOOP_INTERVAL": "180",
                "DEFAULT_PHONE_NUMBER": "+44XXXXXXXXXX",
                "DEFAULT_VOICE_MODE": "mode_c",
                "BEDROCK_REGION": bedrock_config.get("region", "eu-west-1"),
                "BEDROCK_MODEL_ID": bedrock_config.get("models", {}).get("standard", {}).get(
                    "model_id", "eu.anthropic.claude-sonnet-4-6"
                ),
                "NOVA_SONIC_MODEL_ID": bedrock_config.get("models", {}).get("voice", {}).get(
                    "model_id", "amazon.nova-sonic-v1:0"
                ),
                "NOVA_SONIC_REGION": "us-east-1",
                "VOICE_PASSPHRASE": "REDACTED_PASSPHRASE",
                "VOICE_SESSION_TIMEOUT": "90",
                "DDB_TABLE_NAME": infrastructure.main_table.table_name,
                "TWILIO_SECRET_ARN": twilio_secret_arn,
                "AGENTCORE_RUNTIME_ARN": env_context.get("agentcore", {}).get(
                    "runtime_arn", ""
                ),
                "AGENTCORE_REGION": env_context.get("region", "eu-west-1"),
                "API_TOKEN": env_context.get("api_token", ""),
                "RDS_CLUSTER_ENDPOINT": self.aurora_cluster.cluster_endpoint.hostname,
                "RDS_SECRET_ARN": self.aurora_cluster.secret.secret_arn,
                "RDS_CLUSTER_ID": f"{project_name}-rds-aurora-cluster-{env_name}",
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(10),
            ),
        )
        container.add_port_mappings(ecs.PortMapping(container_port=8080, protocol=ecs.Protocol.TCP))

        # Security group for the service
        service_sg = ec2.SecurityGroup(
            self, f"ServiceSg-{env_name}",
            security_group_name=f"{project_name}-backend-sg-ecs-{env_name}",
            vpc=self.vpc,
            allow_all_outbound=True,
        )

        # Allow ECS tasks to reach Aurora on port 3306
        self.rds_sg.add_ingress_rule(
            peer=service_sg,
            connection=ec2.Port.tcp(3306),
            description="MySQL from ECS tasks",
        )

        # ECS Service
        self.service = ecs.FargateService(
            self, f"Service-{env_name}",
            service_name=f"{project_name}-backend-ecs-agent-svc-{env_name}",
            cluster=self.cluster,
            task_definition=self.task_definition,
            desired_count=ecs_config.get("desired_count", 1),
            security_groups=[service_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )

        # NLB for WebSocket (TCP passthrough — no HTTP upgrade issues)
        # Internet-facing so browser can connect directly for the demo
        nlb = elbv2.NetworkLoadBalancer(
            self, f"NlbPub-{env_name}",
            load_balancer_name=f"{project_name}-nlb-ws-pub-{env_name}",
            vpc=self.vpc,
            internet_facing=True,
        )

        # TLS listener (443) — terminates TLS, forwards to ECS on port 8080
        tls_cert_arn = env_context.get("nlb_cert_arn", "")
        if not tls_cert_arn:
            raise ValueError("CDK context 'nlb_cert_arn' is required. Set it in cdk.json under the environment context.")

        from aws_cdk import aws_certificatemanager as acm
        cert = acm.Certificate.from_certificate_arn(self, f"NlbCert-{env_name}", tls_cert_arn)

        tls_listener = nlb.add_listener(
            f"WsTlsListener-{env_name}",
            port=443,
            protocol=elbv2.Protocol.TLS,
            certificates=[elbv2.ListenerCertificate.from_arn(tls_cert_arn)],
        )

        tls_listener.add_targets(
            f"WsTlsTarget-{env_name}",
            port=8080,
            protocol=elbv2.Protocol.TCP,
            targets=[self.service],
            target_group_name=f"{project_name}-tg-wss-pub-{env_name}",
            health_check=elbv2.HealthCheck(
                port="8080",
                protocol=elbv2.Protocol.HTTP,
                path="/health",
                interval=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
        )

        # Allow NLB to reach service (internet-facing NLB preserves client IPs)
        service_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8080))

        # Store NLB DNS for use by frontend build
        self.nlb_dns = nlb.load_balancer_dns_name

        # Outputs
        CfnOutput(self, "ClusterName", value=self.cluster.cluster_name)
        CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
        CfnOutput(self, "NlbDns", value=nlb.load_balancer_dns_name)
        CfnOutput(self, "WsUrl", value=f"wss://{nlb.load_balancer_dns_name}/ws")
        CfnOutput(self, "ServiceName", value=self.service.service_name)
        CfnOutput(self, "RdsClusterEndpoint", value=self.aurora_cluster.cluster_endpoint.hostname)
        CfnOutput(self, "RdsSecretArn", value=self.aurora_cluster.secret.secret_arn)
