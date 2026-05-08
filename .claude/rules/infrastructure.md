# Infrastructure Rules

- All resources defined in CDK — never AWS CLI or CloudFormation directly.
- One CDK stack per logical service.
- Lambda functions use PythonFunction (aws_cdk.aws_lambda_python_alpha).
- All Lambdas include the common_utils layer.
- Environment variables set in CDK, read at runtime via os.environ.
- Secrets via Secrets Manager (ARN in env var), config via SSM Parameter Store.
- S3 buckets: versioned, encrypted (S3-managed), SSL enforced, public access blocked.
- DynamoDB: PAY_PER_REQUEST billing, RemovalPolicy.RETAIN, point-in-time recovery.
- No public access by default — every resource must be private unless user confirms.
- ALBs: `internal=True` by default.
- Security groups: never allow inbound from `0.0.0.0/0` without user confirmation.
- Lambda function URLs: do not create. Use API Gateway with authentication.
- CloudFront distributions: always confirm with user before creating.
