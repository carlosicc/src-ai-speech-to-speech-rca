import json
import logging
from typing import Any

from shared.config import VOICE_PASSPHRASE
from shared.state import Phase, demo_state

logger = logging.getLogger(__name__)

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "authenticate_user",
            "description": (
                "Verify the on-call DBA's identity using their voice passphrase. "
                "Call this when the user provides their authentication passphrase."
            ),
            "inputSchema": {
                "json": json.dumps({
                    "type": "object",
                    "properties": {
                        "passphrase": {
                            "type": "string",
                            "description": "The spoken passphrase from the user",
                        }
                    },
                    "required": ["passphrase"],
                })
            },
        }
    },
    {
        "toolSpec": {
            "name": "restore_connectivity",
            "description": (
                "Restore network connectivity by re-adding the firewall rule for port 3306. "
                "Only call this after the user has been authenticated and explicitly authorizes the restore."
            ),
            "inputSchema": {
                "json": json.dumps({
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "The service to restore connectivity for",
                            "default": "aurora-db",
                        },
                        "confirmation": {
                            "type": "string",
                            "description": "The user's verbal confirmation to proceed",
                        },
                    },
                    "required": ["service"],
                })
            },
        }
    },
    {
        "toolSpec": {
            "name": "check_service_health",
            "description": (
                "Check the current health status and metrics of a service. "
                "Use this to report the current state of the affected system to the user."
            ),
            "inputSchema": {
                "json": json.dumps({
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "The service to check health for",
                            "default": "aurora-db",
                        }
                    },
                    "required": ["service"],
                })
            },
        }
    },
]


async def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    logger.info(f"Executing voice tool: {tool_name} with input: {tool_input}")

    if tool_name == "authenticate_user":
        return _authenticate_user(tool_input.get("passphrase", ""))
    elif tool_name == "restore_connectivity":
        return await _restore_connectivity(tool_input.get("service", "aurora-db"))
    elif tool_name == "check_service_health":
        return _check_service_health(tool_input.get("service", "aurora-db"))
    else:
        return {"status": "error", "error": f"Unknown tool: {tool_name}"}


def _authenticate_user(passphrase: str) -> dict[str, Any]:
    normalized = passphrase.strip().lower()
    expected = VOICE_PASSPHRASE.strip().lower()

    if normalized == expected or expected in normalized:
        logger.info("Voice authentication successful")
        return {
            "status": "authenticated",
            "message": "Identity verified successfully. You are now authorized to execute recovery actions.",
        }
    else:
        logger.warning(f"Voice authentication failed: '{normalized}' != '{expected}'")
        return {
            "status": "failed",
            "message": "Authentication failed. Passphrase did not match. Please try again.",
        }


async def _restore_connectivity(service: str) -> dict[str, Any]:
    from shared.network_operations import restore_db_access

    restore_result = await restore_db_access()
    logger.info(f"restore_db_access result: {restore_result}")

    if restore_result["status"] == "error":
        from agents.diagnosis_agent import _broadcast_aws_error
        _broadcast_aws_error("restore_connectivity", Exception(restore_result["message"]))

    if demo_state.phase == Phase.CALLING:
        demo_state.phase = Phase.RECOVERING
        logger.info(f"Firewall rule restored for {service}, advancing to RECOVERING")
        return {
            "status": "success",
            "message": f"Firewall rule restored for {service}. Port 3306 inbound re-added — connectivity recovered instantly.",
        }
    else:
        return {
            "status": "success",
            "message": f"Firewall rule restored for {service}. Security group rule re-added.",
        }


def _check_service_health(service: str) -> dict[str, Any]:
    incident = demo_state.incident
    if incident and incident.service == service and demo_state.phase in (Phase.CALLING, Phase.DIAGNOSING):
        return {
            "service": service,
            "status": "CRITICAL",
            "cpu_percent": 98,
            "memory_percent": 94,
            "iops": 0,
            "connections_active": 0,
            "connections_max": 500,
            "error": "Connection pool exhausted. All connections in CLOSE_WAIT state.",
        }
    else:
        return {
            "service": service,
            "status": "HEALTHY",
            "cpu_percent": 35,
            "memory_percent": 45,
            "iops": 3200,
            "connections_active": 120,
            "connections_max": 500,
        }
