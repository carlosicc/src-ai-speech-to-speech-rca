from constructs import Construct
from aws_cdk import Stack, CfnOutput


class FrontendStack(Stack):
    """Frontend hosting stack — S3 + CloudFront.

    NOTE: CloudFront is inherently public. This stack should only be
    deployed after explicit user confirmation of public access.
    """

    def __init__(self, scope: Construct, construct_id: str,
                 env_name: str, env_context: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_name = env_context.get("project_name", "rca")

        # CloudFront + S3 hosting will be added here after user confirms
        # public access is acceptable for the demo frontend.
        CfnOutput(self, "Status", value="pending-user-confirmation-for-public-access")
