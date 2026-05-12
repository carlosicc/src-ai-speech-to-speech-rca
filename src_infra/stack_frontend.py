import os

from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput, RemovalPolicy, Duration,
    aws_s3 as s3,
    aws_s3_deployment as s3_deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_lambda as lambda_,
)


BASIC_AUTH_FUNCTION_CODE = """
function handler(event) {
  var request = event.request;
  var headers = request.headers;
  var authString = "Basic CREDENTIALS_PLACEHOLDER";

  if (
    typeof headers.authorization === "undefined" ||
    headers.authorization.value !== authString
  ) {
    return {
      statusCode: 401,
      statusDescription: "Unauthorized",
      headers: {
        "www-authenticate": { value: "Basic realm=\\"RCA Demo\\"" },
      },
    };
  }

  return request;
}
"""


class FrontendStack(Stack):
    """Frontend hosting stack — S3 + CloudFront with basic auth for the React demo app."""

    def __init__(self, scope: Construct, construct_id: str,
                 env_name: str, env_context: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_name = env_context.get("project_name", "rca")
        account_id = Stack.of(self).account
        region = Stack.of(self).region

        # Demo credentials (base64 of "demo:REDACTED_PASSWORD")
        import base64
        demo_user = "demo"
        demo_pass = "REDACTED_PASSWORD"
        credentials_b64 = base64.b64encode(f"{demo_user}:{demo_pass}".encode()).decode()

        # S3 bucket for static frontend assets
        site_bucket = s3.Bucket(
            self, f"SiteBucket-{env_name}",
            bucket_name=f"{project_name}-frontend-site-{account_id}-{region}-{env_name}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Origin Access Identity for CloudFront → S3
        oai = cloudfront.OriginAccessIdentity(
            self, f"OAI-{env_name}",
            comment=f"{project_name} frontend OAI {env_name}",
        )
        site_bucket.grant_read(oai)

        # CloudFront Function for basic auth
        auth_function_code = BASIC_AUTH_FUNCTION_CODE.replace(
            "CREDENTIALS_PLACEHOLDER", credentials_b64
        )
        auth_function = cloudfront.Function(
            self, f"AuthFunction-{env_name}",
            function_name=f"{project_name}-cf-auth-{env_name}",
            code=cloudfront.FunctionCode.from_inline(auth_function_code),
            runtime=cloudfront.FunctionRuntime.JS_2_0,
        )

        # CloudFront distribution
        distribution = cloudfront.Distribution(
            self, f"Distribution-{env_name}",
            comment=f"{project_name} frontend {env_name}",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(site_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                function_associations=[
                    cloudfront.FunctionAssociation(
                        function=auth_function,
                        event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                    ),
                ],
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_page_path="/index.html",
                    response_http_status=200,
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_page_path="/index.html",
                    response_http_status=200,
                    ttl=Duration.seconds(0),
                ),
            ],
        )

        # Deploy built frontend to S3
        frontend_dist_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "src_frontend", "app", "dist"
        )
        s3_deploy.BucketDeployment(
            self, f"DeployFrontend-{env_name}",
            sources=[s3_deploy.Source.asset(frontend_dist_path)],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # Outputs
        CfnOutput(self, "CloudFrontUrl",
                  value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "BucketName", value=site_bucket.bucket_name)
        CfnOutput(self, "DistributionId", value=distribution.distribution_id)
        CfnOutput(self, "DemoCredentials",
                  value=f"Username: {demo_user} / Password: {demo_pass}")
