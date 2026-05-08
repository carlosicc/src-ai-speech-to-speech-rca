import logging
from typing import Dict, Any, Optional, List

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)
_dynamodb = boto3.resource("dynamodb")
_TABLE_CACHE: Dict[str, Any] = {}


def get_table(table_name: str):
    """Get DynamoDB Table resource (cached)."""
    if table_name not in _TABLE_CACHE:
        _TABLE_CACHE[table_name] = _dynamodb.Table(table_name)
    return _TABLE_CACHE[table_name]


def get_item(table_name: str, pk: str, sk: str,
             consistent_read: bool = False) -> Optional[Dict[str, Any]]:
    """Get single item by primary key."""
    table = get_table(table_name)
    try:
        response = table.get_item(Key={"PK": pk, "SK": sk}, ConsistentRead=consistent_read)
        return response.get("Item")
    except Exception as e:
        logger.error(f"get_item failed for {pk}#{sk}: {e}")
        return None


def put_item(table_name: str, item: Dict[str, Any]) -> None:
    """Put item (validates PK and SK are present)."""
    if "PK" not in item or "SK" not in item:
        raise ValueError("Item must include 'PK' and 'SK'")
    table = get_table(table_name)
    table.put_item(Item=item)
    logger.info(f"put_item: {item['PK']}#{item['SK']}")


def query_items(table_name: str, pk: str, sk_prefix: Optional[str] = None,
                limit: int = 100, index_name: Optional[str] = None,
                scan_forward: bool = False) -> List[Dict[str, Any]]:
    """Query by partition key with optional sort key prefix filter."""
    table = get_table(table_name)
    key_condition = Key("PK").eq(pk)
    if sk_prefix:
        key_condition = key_condition & Key("SK").begins_with(sk_prefix)

    kwargs = {
        "KeyConditionExpression": key_condition,
        "Limit": limit,
        "ScanIndexForward": scan_forward,
    }
    if index_name:
        kwargs["IndexName"] = index_name

    try:
        response = table.query(**kwargs)
        return response.get("Items", [])
    except Exception as e:
        logger.error(f"query_items failed for {pk}: {e}")
        return []
