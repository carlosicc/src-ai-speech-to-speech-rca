"""Deploy SSM parameters from YAML configuration."""

import argparse
import logging
from pathlib import Path

import boto3
import yaml

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_NAME = "rca"


def deploy_parameters(env_name: str, region: str = "eu-west-1") -> None:
    """Deploy SSM parameters from yaml config."""
    client = boto3.client("ssm", region_name=region)

    config_path = Path(__file__).parent.parent / "environments" / "ssm_parameters.yaml"
    config = yaml.safe_load(config_path.read_text())

    for param in config.get("parameters", []):
        param_name = f"/{PROJECT_NAME}/{env_name}/{param['name']}"
        try:
            client.put_parameter(
                Name=param_name,
                Value=param["value"],
                Type="String",
                Overwrite=True,
            )
            logger.info(f"Set parameter: {param_name}")
        except Exception as e:
            logger.error(f"Failed to set {param_name}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy SSM parameters")
    parser.add_argument("--env", required=True, help="Environment name (e.g., dev01)")
    parser.add_argument("--region", default="eu-west-1", help="AWS region")
    args = parser.parse_args()

    deploy_parameters(args.env, args.region)
