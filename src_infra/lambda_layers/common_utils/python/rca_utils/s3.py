import json
import logging
from typing import Optional, Any

import boto3

logger = logging.getLogger(__name__)
_s3 = boto3.client("s3")


def download_text(bucket: str, key: str) -> Optional[str]:
    """Download text content from S3."""
    try:
        response = _s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")
    except Exception as e:
        logger.error(f"download_text failed for s3://{bucket}/{key}: {e}")
        return None


def upload_text(bucket: str, key: str, content: str,
                content_type: str = "text/plain") -> bool:
    """Upload text content to S3."""
    try:
        _s3.put_object(
            Bucket=bucket, Key=key,
            Body=content.encode("utf-8"),
            ContentType=content_type,
        )
        logger.info(f"upload_text: s3://{bucket}/{key}")
        return True
    except Exception as e:
        logger.error(f"upload_text failed for s3://{bucket}/{key}: {e}")
        return False


def upload_json(bucket: str, key: str, data: Any) -> bool:
    """Upload JSON content to S3."""
    return upload_text(bucket, key, json.dumps(data, default=str), "application/json")
