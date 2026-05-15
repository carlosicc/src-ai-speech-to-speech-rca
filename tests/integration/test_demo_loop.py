"""5-loop reliability test for the demo cycle.

Verifies that 5 consecutive break/fix loops complete without errors,
with mocked AWS calls and mocked LLM agent responses.
"""
import asyncio
import logging
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from shared.state import DemoState, Phase, demo_state


EXPECTED_PHASE_SEQUENCE = [
    Phase.HEALTHY,
    Phase.INCIDENT_DETECTED,
    Phase.DIAGNOSING,
    Phase.CALLING,
    Phase.RECOVERING,
    Phase.RESOLVED,
    Phase.HEALTHY,
]


@pytest.fixture(autouse=True)
def reset_state():
    demo_state.reset()
    demo_state.auto_advance = False
    demo_state.voice_mode = "mode_b"
    demo_state.phone_number = "+44XXXXXXXXXX"
    yield
    demo_state.reset()


@pytest.fixture
def mock_aws():
    """Mock all AWS EC2 calls for SG operations."""
    mock_client = MagicMock()
    mock_client.revoke_security_group_ingress = MagicMock(return_value={})
    mock_client.authorize_security_group_ingress = MagicMock(return_value={})
    mock_client.describe_security_groups = MagicMock(return_value={
        "SecurityGroups": [{
            "IpPermissions": [{
                "FromPort": 3306,
                "ToPort": 3306,
                "IpProtocol": "tcp",
                "UserIdGroupPairs": [{"GroupId": "sg-YYYYYYYYYYYYYYYYY"}],
            }]
        }]
    })

    with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_master_agent():
    """Mock the master agent orchestration to advance phases without LLM calls."""

    async def fake_orchestration(service: str, incident_id: str) -> None:
        from websocket_server import manager
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": f"[MOCK] Diagnosis complete for {service}", "level": "info"},
        })

    with patch("agents.master_agent.run_master_orchestration", side_effect=fake_orchestration):
        with patch("agents.master_agent.run_master_orchestration_fallback", side_effect=fake_orchestration):
            yield


@pytest.fixture
def mock_voice():
    """Mock the voice session — auto-advance phase out of CALLING after a short delay."""
    from voice.voice_router import VoiceRouter

    async def fake_start_session(**kwargs):
        await asyncio.sleep(0.1)
        if demo_state.phase == Phase.CALLING:
            demo_state.advance_phase()

    with patch("voice.voice_router.voice_router.start_session", side_effect=fake_start_session):
        with patch("voice.voice_router.voice_router.stop_session", new_callable=AsyncMock):
            with patch.object(VoiceRouter, "active", new_callable=lambda: property(lambda self: False)):
                yield


class TestDemoLoopReliability:
    @pytest.mark.asyncio
    async def test_five_consecutive_loops(self, mock_aws, mock_master_agent, mock_voice, caplog):
        """Run the full demo loop 5 times — each must complete HEALTHY → ... → HEALTHY."""
        from demo_controller import demo_controller, PHASE_DURATIONS
        from websocket_server import manager

        manager.active_connections = []

        # Wire up broadcast (no-op since no real WS connections)
        from agents.master_agent import set_broadcast
        from agents.diagnosis_agent import set_diagnosis_broadcast
        set_broadcast(manager.broadcast, AsyncMock())
        set_diagnosis_broadcast(manager.broadcast)

        for loop_num in range(5):
            assert demo_state.phase == Phase.HEALTHY, (
                f"Loop {loop_num + 1}: expected HEALTHY at start, got {demo_state.phase}"
            )

            start_time = time.monotonic()
            phases_seen: list[Phase] = [Phase.HEALTHY]

            # Trigger the incident (simulates "Break DB" button)
            demo_state.trigger_incident("aurora-db")
            phases_seen.append(demo_state.phase)

            # Run the phase progression
            task = asyncio.create_task(demo_controller._run_phases())

            # Wait for completion with a 30s timeout
            try:
                await asyncio.wait_for(task, timeout=30.0)
            except asyncio.TimeoutError:
                task.cancel()
                pytest.fail(f"Loop {loop_num + 1}: timed out after 30s (stuck at {demo_state.phase})")

            elapsed = time.monotonic() - start_time

            # Should be back to HEALTHY
            assert demo_state.phase == Phase.HEALTHY, (
                f"Loop {loop_num + 1}: expected HEALTHY at end, got {demo_state.phase}"
            )
            assert elapsed < 30.0, f"Loop {loop_num + 1}: took {elapsed:.1f}s (max 30s)"

            # Reset for next loop
            demo_state.reset()

        # Check no ERROR-level logs were emitted during loops
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) == 0, (
            f"Unexpected errors during loops: {[r.message for r in error_records]}"
        )

    @pytest.mark.asyncio
    async def test_phase_durations_are_tuned(self):
        """Verify phase durations match Phase 6 spec."""
        from demo_controller import PHASE_DURATIONS

        assert PHASE_DURATIONS[Phase.INCIDENT_DETECTED] == 2.0
        assert PHASE_DURATIONS[Phase.DIAGNOSING] == 0.0
        assert PHASE_DURATIONS[Phase.CALLING] == 0.0
        assert PHASE_DURATIONS[Phase.RECOVERING] == 3.0
        assert PHASE_DURATIONS[Phase.RESOLVED] == 2.0

    @pytest.mark.asyncio
    async def test_startup_precheck_restores_missing_rule(self):
        """Verify the startup pre-check detects missing SG rule and restores it."""
        from shared.network_operations import check_sg_rule_exists, restore_db_access

        mock_client = MagicMock()
        mock_client.describe_security_groups = MagicMock(return_value={
            "SecurityGroups": [{"IpPermissions": []}]
        })
        mock_client.authorize_security_group_ingress = MagicMock(return_value={})

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            rule_exists = await check_sg_rule_exists()
            assert rule_exists is False

            result = await restore_db_access()
            assert result["status"] == "success"

        mock_client.authorize_security_group_ingress.assert_called_once()
