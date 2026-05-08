import aws_cdk as cdk
from aws_cdk import assertions

from src_infra.stack_infrastructure import InfrastructureStack


def test_dynamodb_table_created():
    """Verify the main DynamoDB table is created with correct config."""
    app = cdk.App()
    stack = InfrastructureStack(
        app, "TestInfraStack",
        env_name="test",
        env_context={"project_name": "rca"},
    )
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "rca-ddb-table-app-test",
        "BillingMode": "PAY_PER_REQUEST",
        "KeySchema": [
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
    })


def test_s3_bucket_blocks_public_access():
    """Verify S3 bucket has public access blocked."""
    app = cdk.App()
    stack = InfrastructureStack(
        app, "TestInfraStack",
        env_name="test",
        env_context={"project_name": "rca"},
    )
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        },
    })
