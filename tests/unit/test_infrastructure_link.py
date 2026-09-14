import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from shared.state import LinkStatus, Phase, demo_state


@pytest.fixture(autouse=True)
def reset_state():
    demo_state.reset()
    demo_state.link_status = LinkStatus.CONNECTED
    yield
    demo_state.reset()
    demo_state.link_status = LinkStatus.CONNECTED


def _link_messages(mock_broadcast) -> list[dict]:
    return [
        c.args[0]["payload"]
        for c in mock_broadcast.call_args_list
        if c.args[0]["type"] == "infrastructure_link_update"
    ]


def _statuses(mock_broadcast) -> list[str]:
    return [p["status"] for p in _link_messages(mock_broadcast)]


class TestLinkState:
    def test_default_link_status_is_connected(self):
        assert demo_state.link_status == LinkStatus.CONNECTED

    def test_system_status_includes_link(self):
        from websocket_server import build_system_status

        demo_state.link_status = LinkStatus.DISCONNECTED
        payload = build_system_status(demo_state)["payload"]
        assert payload["infrastructure_links"] == [{
            "id": "ecs-aurora",
            "source": "ecs-cluster",
            "target": "aurora-db",
            "protocol": "tcp",
            "port": 3306,
            "status": "disconnected",
        }]

    def test_build_link_update_includes_request_id_when_given(self):
        from websocket_server import build_link_update

        msg = build_link_update("disconnecting", request_id="req-1", message="m")
        assert msg["type"] == "infrastructure_link_update"
        assert msg["payload"] == {
            "link_id": "ecs-aurora",
            "status": "disconnecting",
            "message": "m",
            "request_id": "req-1",
        }

    def test_build_link_update_omits_request_id_when_none(self):
        from websocket_server import build_link_update

        msg = build_link_update("connected")
        assert "request_id" not in msg["payload"]
        assert msg["payload"]["message"] == ""

    @pytest.mark.asyncio
    async def test_set_link_status_updates_state_and_broadcasts(self):
        from websocket_server import set_link_status

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc:
            await set_link_status(LinkStatus.RESTORING, request_id=None, message="x")

        assert demo_state.link_status == LinkStatus.RESTORING
        assert _statuses(mock_bc) == ["restoring"]


class TestBreakDatabaseLinkEvents:
    @pytest.mark.asyncio
    async def test_success_broadcasts_disconnecting_then_disconnected(self):
        from websocket_server import handle_client_message

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock,
                   return_value={"status": "success", "message": "removed"}), \
             patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
            await handle_client_message(json.dumps({
                "type": "break_database",
                "payload": {"request_id": "req-1", "source": "datacenter_3d", "link_id": "ecs-aurora"},
            }))

        assert _statuses(mock_bc) == ["disconnecting", "disconnected"]
        assert all(p["request_id"] == "req-1" for p in _link_messages(mock_bc))
        assert demo_state.link_status == LinkStatus.DISCONNECTED
        mock_trigger.assert_called_once_with("aurora-db")

    @pytest.mark.asyncio
    async def test_already_revoked_counts_as_disconnected(self):
        from websocket_server import handle_client_message

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock,
                   return_value={"status": "already_revoked", "message": "absent"}), \
             patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
            await handle_client_message(json.dumps({"type": "break_database", "payload": {}}))

        assert _statuses(mock_bc) == ["disconnecting", "disconnected"]
        mock_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_aws_error_broadcasts_error_and_rolls_back(self):
        from websocket_server import handle_client_message

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock,
                   return_value={"status": "error", "message": "boom"}), \
             patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
            await handle_client_message(json.dumps({"type": "break_database", "payload": {"request_id": "req-2"}}))

        assert _statuses(mock_bc) == ["disconnecting", "error"]
        assert _link_messages(mock_bc)[-1]["message"] == "boom"
        assert demo_state.link_status == LinkStatus.CONNECTED
        mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_break_while_disconnecting_is_ignored(self):
        from websocket_server import handle_client_message

        demo_state.link_status = LinkStatus.DISCONNECTING
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock) as mock_revoke:
            await handle_client_message(json.dumps({"type": "break_database", "payload": {"request_id": "req-3"}}))

        mock_revoke.assert_not_called()
        assert _statuses(mock_bc) == []

    @pytest.mark.asyncio
    async def test_empty_payload_is_still_accepted(self):
        from websocket_server import handle_client_message

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock,
                   return_value={"status": "success", "message": "removed"}), \
             patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock):
            await handle_client_message(json.dumps({"type": "break_database", "payload": {}}))

        assert _statuses(mock_bc) == ["disconnecting", "disconnected"]
        assert all("request_id" not in p for p in _link_messages(mock_bc))
