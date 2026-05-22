"""Voice agent tools for AgentCore BidiAgent.

These mirror the tools in voice_tools.py but are self-contained
for the AgentCore container (no shared imports from parent backend).
"""

import logging
import os

from strands import tool

logger = logging.getLogger(__name__)

VOICE_PASSPHRASE = os.environ.get("VOICE_PASSPHRASE", "REDACTED_PASSPHRASE")


@tool
def authenticate_user(spoken_passphrase: str) -> dict:
    """Authenticate the on-call DBA by verifying their voice passphrase.

    Args:
        spoken_passphrase: The passphrase spoken by the user.

    Returns:
        Authentication result with status and message.
    """
    normalized = spoken_passphrase.lower().strip()
    expected = VOICE_PASSPHRASE.lower().strip()

    if expected in normalized or normalized in expected:
        logger.info("Voice authentication PASSED")
        return {
            "authenticated": True,
            "message": "Identity verified. You are authorized to proceed.",
        }
    else:
        logger.info(f"Voice authentication FAILED: '{normalized}' != '{expected}'")
        return {
            "authenticated": False,
            "message": "Passphrase did not match. Please try again.",
        }


@tool
def apply_network_fix(service: str = "aurora-db") -> dict:
    """Apply the network fix to recover database connectivity.

    Args:
        service: The database service to fix connectivity for.

    Returns:
        Fix operation result.
    """
    logger.info(f"apply_network_fix tool called for {service}")
    return {
        "status": "success",
        "service": service,
        "message": f"Network fix applied for {service}. Firewall rule re-added, connections recovering. ETA 30 seconds to full recovery.",
    }


@tool
def check_service_health(service: str = "aurora-db") -> dict:
    """Check the current health status of a service.

    Args:
        service: The service to check health for.

    Returns:
        Current health status including metrics.
    """
    logger.info(f"check_service_health tool called for {service}")
    return {
        "service": service,
        "status": "CRITICAL",
        "cpu_percent": 98,
        "memory_percent": 94,
        "active_connections": 0,
        "max_connections": 100,
        "error": "Connection pool exhausted. All 100 connections in use, 47 requests queuing.",
        "last_healthy": "2026-05-12T14:48:00Z",
        "downtime_seconds": 180,
    }
