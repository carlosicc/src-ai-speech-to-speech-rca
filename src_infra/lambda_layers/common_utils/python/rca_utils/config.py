import os
import logging
from functools import lru_cache
from typing import Optional

import boto3

logger = logging.getLogger(__name__)
ssm = boto3.client("ssm")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev01")
PROJECT_NAME = "rca"


@lru_cache(maxsize=256)
def get_parameter(param_name: str, default: Optional[str] = None) -> str:
    """Get SSM parameter with LRU caching (persists for Lambda container lifetime)."""
    full_path = f"/{PROJECT_NAME}/{ENVIRONMENT}/{param_name}"
    try:
        response = ssm.get_parameter(Name=full_path)
        return response["Parameter"]["Value"]
    except ssm.exceptions.ParameterNotFound:
        if default is not None:
            logger.warning(f"Parameter {full_path} not found, using default")
            return default
        raise


@lru_cache(maxsize=32)
def get_bedrock_model_id(tier: str = "standard") -> str:
    """Get Bedrock model ID for specified tier (fast, standard, advanced, voice)."""
    return get_parameter(f"bedrock/models/{tier}/model_id")


def get_parameter_int(param_name: str, default: Optional[int] = None) -> int:
    """Get SSM parameter as integer."""
    raw = get_parameter(param_name, str(default) if default is not None else None)
    return int(raw)


def get_parameter_bool(param_name: str, default: Optional[bool] = None) -> bool:
    """Get SSM parameter as boolean."""
    raw = get_parameter(param_name, str(default).lower() if default is not None else None)
    return raw.lower() in ("true", "1", "yes")
