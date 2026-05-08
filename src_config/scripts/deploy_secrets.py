"""Deploy secrets from .env file to AWS Secrets Manager."""

import argparse
import json
import logging
import os
from pathlib import Path

import boto3

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_NAME = "rca"


def load_env_file(env_name: str) -> dict[str, str]:
    """Load key=value pairs from .env.{env} file."""
    env_path = Path(__file__).parent.parent / "environments" / f".env.{env_name}"
    if not env_path.exists():
        raise FileNotFoundError(f"Environment file not found: {env_path}")

    secrets = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if value:
            secrets[key.strip()] = value.strip()
    return secrets


def deploy_secrets(env_name: str, region: str = "eu-west-1") -> None:
    """Deploy secrets to AWS Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=region)
    secrets = load_env_file(env_name)

    secret_name = f"{PROJECT_NAME}/credentials/{env_name}"

    try:
        client.create_secret(
            Name=secret_name,
            SecretString=json.dumps(secrets),
            Description=f"RCA Agent Demo credentials for {env_name}",
        )
        logger.info(f"Created secret: {secret_name}")
    except client.exceptions.ResourceExistsException:
        client.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(secrets),
        )
        logger.info(f"Updated secret: {secret_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy secrets to Secrets Manager")
    parser.add_argument("--env", required=True, help="Environment name (e.g., dev01)")
    parser.add_argument("--region", default="eu-west-1", help="AWS region")
    args = parser.parse_args()

    deploy_secrets(args.env, args.region)
