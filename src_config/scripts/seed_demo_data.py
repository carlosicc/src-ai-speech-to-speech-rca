"""Seed DynamoDB with prompts, souls, and demo configuration."""

import argparse
import json
import logging
import os
from pathlib import Path

import boto3

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

PROJECT_NAME = "rca"


def seed_prompts(table_name: str, region: str = "eu-west-1") -> None:
    """Load prompt JSON files and write to DynamoDB."""
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    prompts_dir = Path(__file__).parent.parent / "prompts"

    for prompt_file in prompts_dir.glob("*_prompt.json"):
        data = json.loads(prompt_file.read_text())
        agent_type = data["agent_type"]

        item = {
            "PK": f"PROMPT#{agent_type}",
            "SK": "LATEST",
            "prompt_text": data["prompt_text"],
            "max_tokens": data.get("max_tokens", 4096),
            "version": "1",
        }
        table.put_item(Item=item)
        logger.info(f"Seeded prompt: PROMPT#{agent_type}")

    for soul_file in prompts_dir.glob("*_soul.json"):
        data = json.loads(soul_file.read_text())
        agent_name = data["agent_name"]

        item = {
            "PK": f"SOUL#{agent_name}",
            "SK": "LATEST",
            **data,
        }
        table.put_item(Item=item)
        logger.info(f"Seeded soul: SOUL#{agent_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data to DynamoDB")
    parser.add_argument("--env", required=True, help="Environment name (e.g., dev01)")
    parser.add_argument("--region", default="eu-west-1", help="AWS region")
    args = parser.parse_args()

    table_name = f"{PROJECT_NAME}-ddb-table-app-{args.env}"
    seed_prompts(table_name, args.region)
