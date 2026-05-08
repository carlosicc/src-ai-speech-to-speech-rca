from constructs import Construct
from aws_cdk import (
    Stack, RemovalPolicy, Aws, CfnOutput, Duration,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_lambda as lambda_,
)
from aws_cdk.aws_lambda_python_alpha import PythonLayerVersion


class InfrastructureStack(Stack):
    """Foundation stack — shared resources for the entire platform."""

    def __init__(self, scope: Construct, construct_id: str,
                 env_name: str, env_context: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_name = env_context.get("project_name", "rca")

        # DynamoDB Single Table
        self.main_table = dynamodb.Table(
            self, f"MainTable-{env_name}",
            table_name=f"{project_name}-ddb-table-app-{env_name}",
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            time_to_live_attribute="expires_at",
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
                recovery_period_in_days=7,
            ),
        )

        # S3 Bucket for raw data (logs, metrics snapshots)
        self.raw_data_bucket = s3.Bucket(
            self, f"RawDataBucket-{env_name}",
            bucket_name=f"{project_name}-s3-raw-data-{Aws.ACCOUNT_ID}-{Aws.REGION}-{env_name}",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
        )

        # Lambda Layer (Shared Utilities)
        self.common_layer = PythonLayerVersion(
            self, f"CommonUtilsLayer-{env_name}",
            entry="src_infra/lambda_layers/common_utils/python",
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared utilities: config, DynamoDB, S3, secrets, models",
            layer_version_name=f"{project_name}-common-utils-{env_name}",
        )

        # Outputs
        CfnOutput(self, "TableName", value=self.main_table.table_name)
        CfnOutput(self, "RawBucketName", value=self.raw_data_bucket.bucket_name)
