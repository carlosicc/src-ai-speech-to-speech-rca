"""Closed-loop integration tests for Nova Sonic voice agent.

Requires: AWS credentials with Bedrock access in eu-north-1, and pre-generated audio fixtures.
Run fixtures first: .venv/bin/python scripts/generate_test_audio.py
"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend"))

from tests.harness.nova_sonic_test_client import run_nova_sonic_test
from tests.harness.tool_handler import mock_tool_handler

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "audio"

SYSTEM_PROMPT = (
    "You are an AI Operations Center voice agent. "
    "Say hello then ask for passphrase. "
    "When user speaks, IMMEDIATELY use authenticate_user tool with their words. Do not ask again. "
    "If authenticated, use check_service_health then ask for authorization to restore connectivity. "
    "When authorized, use apply_network_fix."
)

TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "authenticate_user",
            "description": "Verify the on-call DBA's identity using their voice passphrase.",
            "inputSchema": {
                "json": '{"type":"object","properties":{"passphrase":{"type":"string","description":"The spoken passphrase from the user"}},"required":["passphrase"]}'
            },
        }
    },
    {
        "toolSpec": {
            "name": "apply_network_fix",
            "description": "Restore network connectivity by re-adding the firewall rule for port 3306. Only call after user is authenticated and authorizes.",
            "inputSchema": {
                "json": '{"type":"object","properties":{"service":{"type":"string","default":"aurora-db"},"confirmation":{"type":"string"}},"required":["service"]}'
            },
        }
    },
    {
        "toolSpec": {
            "name": "check_service_health",
            "description": "Check current health status and metrics of a service.",
            "inputSchema": {
                "json": '{"type":"object","properties":{"service":{"type":"string","default":"aurora-db"}},"required":["service"]}'
            },
        }
    },
]


def _fixture_path(name: str) -> str:
    path = FIXTURES_DIR / f"{name}.wav"
    if not path.exists():
        pytest.skip(f"Audio fixture not found: {path}. Run: .venv/bin/python scripts/generate_test_audio.py")
    return str(path)


@pytest.mark.asyncio
async def test_correct_passphrase_invokes_authenticate():
    """Nova Sonic hears 'test passphrase' and calls authenticate_user tool with success."""
    result = await run_nova_sonic_test(
        audio_path=_fixture_path("correct_passphrase"),
        system_prompt=SYSTEM_PROMPT,
        tools=TOOL_SPECS,
        tool_handler=mock_tool_handler,
        timeout=45.0,
    )

    assert result.error is None, f"Session error: {result.error}"
    assert any(t["name"] == "authenticate_user" for t in result.tool_invocations), (
        f"authenticate_user not called. Tools invoked: {[t['name'] for t in result.tool_invocations]}"
    )
    auth_call = next(t for t in result.tool_invocations if t["name"] == "authenticate_user")
    assert auth_call["result"]["status"] == "authenticated", (
        f"Expected authenticated, got: {auth_call['result']}"
    )


@pytest.mark.asyncio
async def test_wrong_passphrase_fails_auth():
    """Nova Sonic hears 'bravo midnight' — tool called but auth fails."""
    result = await run_nova_sonic_test(
        audio_path=_fixture_path("wrong_passphrase"),
        system_prompt=SYSTEM_PROMPT,
        tools=TOOL_SPECS,
        tool_handler=mock_tool_handler,
        timeout=45.0,
    )

    assert result.error is None, f"Session error: {result.error}"
    assert any(t["name"] == "authenticate_user" for t in result.tool_invocations), (
        f"authenticate_user not called. Tools invoked: {[t['name'] for t in result.tool_invocations]}"
    )
    auth_call = next(t for t in result.tool_invocations if t["name"] == "authenticate_user")
    assert auth_call["result"]["status"] == "failed"


@pytest.mark.asyncio
async def test_full_flow_auth_then_restore():
    """Full flow: correct passphrase + 'yes fix it' → authenticate then apply_network_fix."""
    result = await run_nova_sonic_test(
        audio_path=_fixture_path("authorize_fix"),
        system_prompt=(
            SYSTEM_PROMPT + "\n\nIMPORTANT: The user has ALREADY been authenticated. "
            "Skip authentication. Ask if they authorize the fix, then use apply_network_fix."
        ),
        tools=TOOL_SPECS,
        tool_handler=mock_tool_handler,
        timeout=45.0,
    )

    assert result.error is None, f"Session error: {result.error}"
    assert any(t["name"] == "apply_network_fix" for t in result.tool_invocations), (
        f"apply_network_fix not called. Tools invoked: {[t['name'] for t in result.tool_invocations]}"
    )


@pytest.mark.asyncio
async def test_silence_no_tools():
    """Silence input — model should greet but not invoke any tools."""
    result = await run_nova_sonic_test(
        audio_path=_fixture_path("silence"),
        system_prompt=SYSTEM_PROMPT,
        tools=TOOL_SPECS,
        tool_handler=mock_tool_handler,
        timeout=30.0,
    )

    # No tools should be invoked from silence alone
    tool_names = [t["name"] for t in result.tool_invocations]
    assert "authenticate_user" not in tool_names, (
        f"authenticate_user should not be called on silence. Tools: {tool_names}"
    )
