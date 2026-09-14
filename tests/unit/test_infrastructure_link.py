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
