import json
import logging
from functools import lru_cache
from typing import Dict, Any

import boto3

logger = logging.getLogger(__name__)
_secrets_client = boto3.client("secretsmanager")


@lru_cache(maxsize=32)
def get_secret(secret_arn: str) -> Dict[str, Any]:
    """Get secret value from Secrets Manager (cached for Lambda container lifetime)."""
    try:
        response = _secrets_client.get_secret_value(SecretId=secret_arn)
        return json.loads(response["SecretString"])
    except Exception as e:
        logger.error(f"get_secret failed for {secret_arn}: {e}")
        raise
