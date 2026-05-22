"""Test tool handler — real auth logic, mocked destructive operations."""
import logging
from typing import Any

logger = logging.getLogger(__name__)

VOICE_PASSPHRASE = "REDACTED_PASSPHRASE"


def _authenticate_user(passphrase: str) -> dict[str, Any]:
    """Same logic as production voice_tools._authenticate_user."""
    normalized = passphrase.strip().lower()
    expected = VOICE_PASSPHRASE.strip().lower()

    if normalized == expected or expected in normalized:
        return {
            "status": "authenticated",
            "message": "Identity verified successfully. You are now authorized to execute recovery actions.",
        }

    expected_words = expected.split()
    if len(expected_words) >= 2 and all(w in normalized for w in expected_words):
        return {
            "status": "authenticated",
            "message": "Identity verified successfully. You are now authorized to execute recovery actions.",
        }

    return {
        "status": "failed",
        "message": "Authentication failed. Passphrase did not match. Please try again.",
    }


def _check_service_health(service: str) -> dict[str, Any]:
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


def _apply_network_fix(service: str) -> dict[str, Any]:
    return {
        "status": "success",
        "message": f"Mock: network fix applied for {service}. Port 3306 inbound re-added.",
    }


async def mock_tool_handler(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Execute tools for testing — real auth, mocked infrastructure ops."""
    logger.info(f"[test_tool_handler] {tool_name}({tool_input})")

    if tool_name == "authenticate_user":
        return _authenticate_user(tool_input.get("passphrase", ""))
    elif tool_name == "check_service_health":
        return _check_service_health(tool_input.get("service", "aurora-db"))
    elif tool_name == "apply_network_fix":
        return _apply_network_fix(tool_input.get("service", "aurora-db"))
    else:
        return {"status": "error", "error": f"Unknown tool: {tool_name}"}
