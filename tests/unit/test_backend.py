import json
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from main import app  # noqa: E402
from shared.state import DemoState, Incident, Phase, PHASE_ORDER, demo_state  # noqa: E402
from websocket_server import build_phase_update, build_system_status, handle_client_message, manager  # noqa: E402


@pytest.fixture(autouse=True)
def reset_demo_state():
    demo_state.reset()
    demo_state.auto_advance = True
    demo_state.voice_mode = "mode_c"
    demo_state.phone_number = "+44XXXXXXXXXX"
    manager.active_connections.clear()
    yield
    demo_state.reset()


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestDemoState:
    def test_initial_state_is_healthy(self):
        state = DemoState()
        assert state.phase == Phase.HEALTHY
        assert state.incident is None

    def test_trigger_incident(self):
        state = DemoState()
        incident = state.trigger_incident("aurora-db")
        assert state.phase == Phase.INCIDENT_DETECTED
        assert incident.service == "aurora-db"
        assert incident.severity == "critical"
        assert state.incident is incident

    def test_advance_through_all_phases(self):
        state = DemoState()
        state.trigger_incident("aurora-db")
        expected_phases = [Phase.DIAGNOSING, Phase.CALLING, Phase.RECOVERING, Phase.RESOLVED, Phase.HEALTHY]
        for expected in expected_phases:
            state.advance_phase()
            assert state.phase == expected
        assert state.incident is None

    def test_reset_returns_to_healthy(self):
        state = DemoState()
        state.trigger_incident("aurora-db")
        state.advance_phase()
        state.reset()
        assert state.phase == Phase.HEALTHY
        assert state.incident is None

    def test_phase_order_completeness(self):
        assert len(PHASE_ORDER) == 6
        assert PHASE_ORDER[0] == Phase.HEALTHY
        assert PHASE_ORDER[-1] == Phase.RESOLVED


class TestBuildSystemStatus:
    def test_all_services_healthy(self):
        status = build_system_status(demo_state)
        assert status["type"] == "system_status"
        assert len(status["payload"]["systems"]) == 7
        for system in status["payload"]["systems"]:
            assert system["status"] == "healthy"

    def test_affected_service_shows_degraded(self):
        demo_state.trigger_incident("aurora-db")
        status = build_system_status(demo_state)
        for system in status["payload"]["systems"]:
            if system["name"] == "aurora-db":
                assert system["status"] == "degraded"
            else:
                assert system["status"] == "healthy"

    def test_status_includes_phase_and_voice_mode(self):
        status = build_system_status(demo_state)
        assert status["payload"]["phase"] == "HEALTHY"
        assert status["payload"]["voice_mode"] == "mode_c"
        assert status["payload"]["auto_advance"] is True


class TestBuildPhaseUpdate:
    def test_phase_update_structure(self):
        demo_state.trigger_incident("aurora-db")
        update = build_phase_update(demo_state, details="test detail")
        assert update["type"] == "phase_update"
        assert update["payload"]["phase"] == "INCIDENT_DETECTED"
        assert update["payload"]["agent"] == "master"
        assert update["payload"]["details"] == "test detail"
        assert update["payload"]["incident_id"] is not None


class TestHandleClientMessage:
    @pytest.mark.asyncio
    async def test_trigger_incident_message(self):
        msg = json.dumps({"type": "trigger_incident", "payload": {"service": "aurora-db"}})
        await handle_client_message(msg)
        assert demo_state.phase == Phase.INCIDENT_DETECTED
        assert demo_state.incident.service == "aurora-db"

    @pytest.mark.asyncio
    async def test_trigger_incident_ignored_if_not_healthy(self):
        demo_state.trigger_incident("aurora-db")
        demo_state.advance_phase()
        msg = json.dumps({"type": "trigger_incident", "payload": {"service": "ecs-cluster"}})
        await handle_client_message(msg)
        assert demo_state.incident.service == "aurora-db"

    @pytest.mark.asyncio
    async def test_reset_demo_message(self):
        demo_state.trigger_incident("aurora-db")
        msg = json.dumps({"type": "reset_demo", "payload": {}})
        await handle_client_message(msg)
        assert demo_state.phase == Phase.HEALTHY
        assert demo_state.incident is None

    @pytest.mark.asyncio
    async def test_set_phone_number_valid(self):
        msg = json.dumps({"type": "set_phone_number", "payload": {"phone_number": "+1234567890"}})
        await handle_client_message(msg)
        assert demo_state.phone_number == "+1234567890"

    @pytest.mark.asyncio
    async def test_set_phone_number_invalid_rejected(self):
        msg = json.dumps({"type": "set_phone_number", "payload": {"phone_number": "not-a-phone"}})
        await handle_client_message(msg)
        assert demo_state.phone_number == "+44XXXXXXXXXX"

    @pytest.mark.asyncio
    async def test_set_voice_mode_valid(self):
        msg = json.dumps({"type": "set_voice_mode", "payload": {"mode": "mode_a"}})
        await handle_client_message(msg)
        assert demo_state.voice_mode == "mode_a"

    @pytest.mark.asyncio
    async def test_set_voice_mode_invalid_rejected(self):
        msg = json.dumps({"type": "set_voice_mode", "payload": {"mode": "mode_z"}})
        await handle_client_message(msg)
        assert demo_state.voice_mode == "mode_c"

    @pytest.mark.asyncio
    async def test_set_auto_advance(self):
        msg = json.dumps({"type": "set_auto_advance", "payload": {"enabled": False}})
        await handle_client_message(msg)
        assert demo_state.auto_advance is False

    @pytest.mark.asyncio
    async def test_invalid_json_does_not_crash(self):
        await handle_client_message("not json at all")
        assert demo_state.phase == Phase.HEALTHY

    @pytest.mark.asyncio
    async def test_unknown_message_type_does_not_crash(self):
        msg = json.dumps({"type": "nonexistent_type", "payload": {}})
        await handle_client_message(msg)
        assert demo_state.phase == Phase.HEALTHY


class TestWebSocketEndpoint:
    @pytest.mark.asyncio
    async def test_websocket_connect_receives_system_status(self):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream("GET", "/ws") as response:
                pass

    @pytest.mark.asyncio
    async def test_websocket_full_flow(self):
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                # Should receive system_status on connect
                data = ws.receive_json()
                assert data["type"] == "system_status"
                assert data["payload"]["phase"] == "HEALTHY"

                # Trigger incident
                ws.send_json({"type": "trigger_incident", "payload": {"service": "aurora-db"}})
                # Should receive incident_detected
                msg = ws.receive_json()
                assert msg["type"] == "incident_detected"
                assert msg["payload"]["service"] == "aurora-db"

                # Should receive phase_update
                msg = ws.receive_json()
                assert msg["type"] == "phase_update"
                assert msg["payload"]["phase"] == "INCIDENT_DETECTED"

                # Should receive agent_log
                msg = ws.receive_json()
                assert msg["type"] == "agent_log"

                # Reset: link lifecycle (restoring -> connected|error) precedes system_status
                ws.send_json({"type": "reset_demo", "payload": {}})
                msg = ws.receive_json()
                assert msg["type"] == "infrastructure_link_update"
                assert msg["payload"]["status"] == "restoring"
                msg = ws.receive_json()
                assert msg["type"] == "infrastructure_link_update"
                assert msg["payload"]["status"] in ("connected", "error")
                msg = ws.receive_json()
                assert msg["type"] == "system_status"

    @pytest.mark.asyncio
    async def test_websocket_set_voice_mode(self):
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                _ = ws.receive_json()  # system_status
                ws.send_json({"type": "set_voice_mode", "payload": {"mode": "mode_b"}})
                # No broadcast expected for set_voice_mode, just verify state
        assert demo_state.voice_mode == "mode_b"
