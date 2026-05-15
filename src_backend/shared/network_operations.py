import asyncio
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.config import ECS_SECURITY_GROUP_ID, RDS_REGION, RDS_SECURITY_GROUP_ID

logger = logging.getLogger(__name__)

_SG_RULE_DESCRIPTION = "MySQL from ECS tasks"
_MYSQL_PORT = 3306


def _get_ec2_client():
    return boto3.client("ec2", region_name=RDS_REGION)


async def revoke_db_access() -> dict[str, Any]:
    """Remove the inbound MySQL rule from the RDS security group (instant break)."""
    if not RDS_SECURITY_GROUP_ID or not ECS_SECURITY_GROUP_ID:
        logger.error("Security group IDs not configured")
        return {"status": "error", "message": "Security group IDs not configured"}

    try:
        client = _get_ec2_client()
        await asyncio.to_thread(
            client.revoke_security_group_ingress,
            GroupId=RDS_SECURITY_GROUP_ID,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": _MYSQL_PORT,
                "ToPort": _MYSQL_PORT,
                "UserIdGroupPairs": [{"GroupId": ECS_SECURITY_GROUP_ID, "Description": _SG_RULE_DESCRIPTION}],
            }],
        )
        logger.info(f"Revoked port {_MYSQL_PORT} ingress from {ECS_SECURITY_GROUP_ID} on {RDS_SECURITY_GROUP_ID}")
        return {"status": "success", "message": "Security group rule removed — database is now unreachable"}
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "InvalidPermission.NotFound":
            logger.warning("Rule already absent — idempotent success")
            return {"status": "already_revoked", "message": "Rule already absent"}
        logger.error(f"Failed to revoke SG rule: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error revoking SG rule: {e}")
        return {"status": "error", "message": str(e)}


async def restore_db_access() -> dict[str, Any]:
    """Re-add the inbound MySQL rule to the RDS security group (instant fix)."""
    if not RDS_SECURITY_GROUP_ID or not ECS_SECURITY_GROUP_ID:
        logger.error("Security group IDs not configured")
        return {"status": "error", "message": "Security group IDs not configured"}

    try:
        client = _get_ec2_client()
        await asyncio.to_thread(
            client.authorize_security_group_ingress,
            GroupId=RDS_SECURITY_GROUP_ID,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": _MYSQL_PORT,
                "ToPort": _MYSQL_PORT,
                "UserIdGroupPairs": [{"GroupId": ECS_SECURITY_GROUP_ID, "Description": _SG_RULE_DESCRIPTION}],
            }],
        )
        logger.info(f"Restored port {_MYSQL_PORT} ingress from {ECS_SECURITY_GROUP_ID} on {RDS_SECURITY_GROUP_ID}")
        return {"status": "success", "message": "Security group rule restored — database connectivity recovered"}
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "InvalidPermission.Duplicate":
            logger.warning("Rule already present — idempotent success")
            return {"status": "already_present", "message": "Rule already present"}
        logger.error(f"Failed to restore SG rule: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error restoring SG rule: {e}")
        return {"status": "error", "message": str(e)}


async def check_sg_rule_exists() -> bool:
    """Check whether the port 3306 inbound rule exists on the RDS security group."""
    if not RDS_SECURITY_GROUP_ID or not ECS_SECURITY_GROUP_ID:
        return False

    try:
        client = _get_ec2_client()
        response = await asyncio.to_thread(
            client.describe_security_groups,
            GroupIds=[RDS_SECURITY_GROUP_ID],
        )
        sg = response["SecurityGroups"][0]
        for perm in sg.get("IpPermissions", []):
            if perm.get("FromPort") == _MYSQL_PORT and perm.get("ToPort") == _MYSQL_PORT:
                for pair in perm.get("UserIdGroupPairs", []):
                    if pair.get("GroupId") == ECS_SECURITY_GROUP_ID:
                        return True
        return False
    except Exception as e:
        logger.error(f"Failed to check SG rule: {e}")
        return False
