"""Tests for Phase 6: Master Agent Orchestration + Polish."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend"))


class TestMasterAgentTools:
    """Test master agent tool functions (sync tools, async broadcasts are fire-and-forget)."""

    def setup_method(self):
        from agents.master_agent import set_broadcast
        set_broadcast(AsyncMock(), AsyncMock())

    def test_assess_severity_critical(self):
        from agents.master_agent import assess_severity
        result = assess_severity(service="aurora-db", incident_id="test-123")
        assert "CRITICAL" in result
        assert "aurora-db" in result
        assert "Immediate escalation" in result

    def test_assess_severity_high(self):
        from agents.master_agent import assess_severity
        result = assess_severity(service="ecs-cluster", incident_id="test-456")
        assert "HIGH" in result

    def test_assess_severity_medium(self):
        from agents.master_agent import assess_severity
        result = assess_severity(service="lambda", incident_id="test-456")
        assert "MEDIUM" in result

    def test_assess_severity_unknown_service(self):
        from agents.master_agent import assess_severity
        result = assess_severity(service="unknown-svc", incident_id="test-789")
        assert "MEDIUM" in result

    def test_activate_voice_call_changes_phase(self):
        from agents.master_agent import activate_voice_call
        from shared.state import Phase, demo_state
        demo_state.phase = Phase.DIAGNOSING
        result = activate_voice_call(
            incident_id="test-123",
            severity="CRITICAL",
            rca_summary="DB overloaded",
        )
        assert "Voice call initiated" in result
        assert demo_state.phase == Phase.CALLING
        demo_state.reset()

    def test_update_incident_status_recovering(self):
        from agents.master_agent import update_incident_status
        from shared.state import Phase, demo_state
        demo_state.phase = Phase.CALLING
        result = update_incident_status(
            incident_id="test-123",
            new_status="recovering",
            resolution="Database restarted",
        )
        assert "recovering" in result
        assert demo_state.phase == Phase.RECOVERING
        demo_state.reset()

    def test_update_incident_status_resolved(self):
        from agents.master_agent import update_incident_status
        from shared.state import Phase, demo_state
        demo_state.phase = Phase.RECOVERING
        result = update_incident_status(
            incident_id="test-123",
            new_status="resolved",
            resolution="All clear",
        )
        assert "resolved" in result
        assert demo_state.phase == Phase.RESOLVED
        demo_state.reset()

    def test_activate_diagnosis_fallback_on_error(self):
        from agents.master_agent import activate_diagnosis
        with patch("agents.diagnosis_agent.run_diagnosis", new_callable=AsyncMock) as mock_diag:
            mock_diag.side_effect = RuntimeError("No credentials")
            result = activate_diagnosis(service="aurora-db", incident_id="test-123")
            assert "aurora-db" in result
            assert "RCA Summary" in result


class TestMasterAgentOrchestration:
    """Test the async orchestration entrypoints."""

    @pytest.mark.asyncio
    async def test_fallback_orchestration_runs_phases(self):
        from agents.master_agent import run_master_orchestration_fallback, set_broadcast
        from shared.state import Phase, demo_state, Incident

        mock_broadcast = AsyncMock()
        mock_phase_change = AsyncMock()
        set_broadcast(mock_broadcast, mock_phase_change)

        demo_state.phase = Phase.DIAGNOSING
        demo_state.incident = Incident(service="aurora-db")

        with patch("agents.diagnosis_agent.run_diagnosis", new_callable=AsyncMock) as mock_diag:
            mock_diag.return_value = "Test RCA"
            rca = await run_master_orchestration_fallback("aurora-db", "inc-001")

        assert "Test RCA" in rca
        assert demo_state.phase == Phase.CALLING
        assert mock_broadcast.call_count >= 4
        demo_state.reset()

    @pytest.mark.asyncio
    async def test_fallback_orchestration_handles_diagnosis_failure(self):
        from agents.master_agent import run_master_orchestration_fallback, set_broadcast
        from shared.state import Phase, demo_state, Incident

        mock_broadcast = AsyncMock()
        mock_phase_change = AsyncMock()
        set_broadcast(mock_broadcast, mock_phase_change)

        demo_state.phase = Phase.DIAGNOSING
        demo_state.incident = Incident(service="aurora-db")

        with patch("agents.diagnosis_agent.run_diagnosis", new_callable=AsyncMock) as mock_diag:
            mock_diag.side_effect = RuntimeError("Bedrock unavailable")
            rca = await run_master_orchestration_fallback("aurora-db", "inc-002")

        assert "RCA Summary" in rca
        assert demo_state.phase == Phase.CALLING
        demo_state.reset()

    @pytest.mark.asyncio
    async def test_master_orchestration_llm_failure_returns_error(self):
        from agents.master_agent import run_master_orchestration, set_broadcast
        from shared.state import Phase, demo_state, Incident
        import agents.master_agent as ma

        mock_broadcast = AsyncMock()
        set_broadcast(mock_broadcast, AsyncMock())
        ma._event_loop = asyncio.get_event_loop()

        demo_state.phase = Phase.DIAGNOSING
        demo_state.incident = Incident(service="aurora-db")

        with patch("agents.master_agent.BedrockModel", side_effect=RuntimeError("No creds")):
            result = await run_master_orchestration("aurora-db", "inc-003")

        assert "error" in result.lower()
        demo_state.reset()


class TestDemoControllerWithMasterAgent:
    """Test demo_controller integration with master agent."""

    @pytest.mark.asyncio
    async def test_trigger_incident_starts_phase_runner(self):
        from demo_controller import demo_controller
        from shared.state import Phase, demo_state
        from websocket_server import manager

        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()
        manager.active_connections = [mock_ws]

        with patch("agents.master_agent.run_master_orchestration", new_callable=AsyncMock) as mock_master:
            mock_master.return_value = "done"
            await demo_controller.trigger_incident("aurora-db", auto=False)
            await asyncio.sleep(0.1)

        assert demo_state.phase != Phase.HEALTHY
        demo_state.reset()
        manager.active_connections = []
        if demo_controller._phase_task:
            demo_controller._phase_task.cancel()

    @pytest.mark.asyncio
    async def test_reset_clears_active_agent(self):
        from shared.state import demo_state
        demo_state.active_agent = "master"
        demo_state.reset()
        assert demo_state.active_agent is None


class TestCancelSimulation:
    """Test that cancel_simulation stops in-progress phase orchestration."""

    @pytest.mark.asyncio
    async def test_cancel_simulation_stops_phase_task(self):
        from demo_controller import DemoController
        from shared.state import Phase, demo_state
        from websocket_server import manager

        ctrl = DemoController()
        mock_ws = AsyncMock()
        mock_ws.send_text = AsyncMock()
        manager.active_connections = [mock_ws]

        with patch("agents.master_agent.run_master_orchestration", new_callable=AsyncMock) as mock_master:
            mock_master.side_effect = asyncio.sleep(60)
            await ctrl.trigger_incident("aurora-db", auto=True)
            await asyncio.sleep(0.05)
            assert ctrl._phase_task is not None
            assert not ctrl._phase_task.done()

            await ctrl.cancel_simulation()
            assert ctrl._phase_task is None
            assert ctrl._auto_triggered is False

        demo_state.reset()
        manager.active_connections = []

    @pytest.mark.asyncio
    async def test_cancel_simulation_noop_when_idle(self):
        from demo_controller import DemoController

        ctrl = DemoController()
        await ctrl.cancel_simulation()
        assert ctrl._phase_task is None


class TestDemoStateActiveAgent:
    """Test active_agent field in DemoState."""

    def test_initial_state_no_active_agent(self):
        from shared.state import DemoState
        state = DemoState()
        assert state.active_agent is None

    def test_reset_clears_active_agent(self):
        from shared.state import DemoState
        state = DemoState()
        state.active_agent = "diagnosis"
        state.reset()
        assert state.active_agent is None


class TestSystemStatusIncludesActiveAgent:
    """Test that system_status WS message includes active_agent."""

    def test_build_system_status_has_active_agent(self):
        from shared.state import DemoState
        from websocket_server import build_system_status

        state = DemoState()
        state.active_agent = "master"
        msg = build_system_status(state)
        assert msg["payload"]["active_agent"] == "master"

    def test_build_system_status_null_agent(self):
        from shared.state import DemoState
        from websocket_server import build_system_status

        state = DemoState()
        msg = build_system_status(state)
        assert msg["payload"]["active_agent"] is None


class TestAgentActivityBroadcast:
    """Test agent_activity message broadcasting."""

    @pytest.mark.asyncio
    async def test_notify_agent_activity_format(self):
        from agents.master_agent import _notify_agent_activity, set_broadcast

        mock_broadcast = AsyncMock()
        set_broadcast(mock_broadcast, AsyncMock())

        await _notify_agent_activity("diagnosis", "running")
        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args[0][0]
        assert call_args["type"] == "agent_activity"
        assert call_args["payload"]["agent"] == "diagnosis"
        assert call_args["payload"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_notify_agent_activity_complete(self):
        from agents.master_agent import _notify_agent_activity, set_broadcast

        mock_broadcast = AsyncMock()
        set_broadcast(mock_broadcast, AsyncMock())

        await _notify_agent_activity("master", "complete")
        call_args = mock_broadcast.call_args[0][0]
        assert call_args["payload"]["status"] == "complete"
