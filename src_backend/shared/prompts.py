import logging
import os
import time
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS: int = 300

_cache: dict[str, tuple[str, float]] = {}


def _get_table():
    table_name = os.environ.get("DDB_TABLE_NAME", "")
    if not table_name:
        return None
    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"))
    return dynamodb.Table(table_name)


def get_prompt(agent_type: str) -> Optional[str]:
    cache_key = f"PROMPT#{agent_type}"
    if cache_key in _cache:
        value, cached_at = _cache[cache_key]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return value

    table = _get_table()
    if table is None:
        logger.warning(f"DDB_TABLE_NAME not set, cannot load prompt for {agent_type}")
        return None

    try:
        response = table.get_item(Key={"PK": f"PROMPT#{agent_type}", "SK": "LATEST"})
        item = response.get("Item")
        if item:
            prompt_text = item.get("prompt_text", "")
            _cache[cache_key] = (prompt_text, time.time())
            return prompt_text
        logger.warning(f"Prompt not found for agent_type={agent_type}")
        return None
    except Exception as e:
        logger.error(f"Failed to load prompt for {agent_type}: {e}")
        return None


def get_soul(agent_name: str) -> Optional[str]:
    cache_key = f"SOUL#{agent_name}"
    if cache_key in _cache:
        value, cached_at = _cache[cache_key]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return value

    table = _get_table()
    if table is None:
        logger.warning(f"DDB_TABLE_NAME not set, cannot load soul for {agent_name}")
        return None

    try:
        response = table.get_item(Key={"PK": f"SOUL#{agent_name}", "SK": "LATEST"})
        item = response.get("Item")
        if item:
            soul_text = item.get("soul_text", "")
            _cache[cache_key] = (soul_text, time.time())
            return soul_text
        logger.warning(f"Soul not found for agent_name={agent_name}")
        return None
    except Exception as e:
        logger.error(f"Failed to load soul for {agent_name}: {e}")
        return None


def clear_cache() -> None:
    _cache.clear()
