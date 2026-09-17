"""Presenter escape hatch for a call that is going nowhere.

A call answered by voicemail keeps the Twilio media stream open, so the idle timer
never fires and the demo sits in CALLING until the far end hangs up (183s observed
on dev01). These tests cover ending that call on demand.
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from shared.state import Phase, demo_state


@pytest.fixture(autouse=True)
def healthy_state():
    demo_state.reset()
    demo_state.phase = Phase.HEALTHY
    yield
    demo_state.reset()
    demo_state.phase = Phase.HEALTHY


def _phases_broadcast(mock_broadcast) -> list[str]:
    return [
        call.args[0]["payload"]["phase"]
        for call in mock_broadcast.await_args_list
        if call.args and call.args[0].get("type") == "phase_update"
    ]


class TestEndCall:
    @pytest.mark.asyncio
    async def test_advances_to_recovering_and_hangs_up(self) -> None:
        from websocket_server import handle_client_message

        demo_state.phase = Phase.CALLING
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("voice.voice_router.voice_router.stop_session", new_callable=AsyncMock) as mock_stop, \
             patch("websocket_server._cancel_inflight_twilio_call", new_callable=AsyncMock) as mock_hangup:
            await handle_client_message(json.dumps({"type": "end_call", "payload": {}}))

        assert demo_state.phase == Phase.RECOVERING
        mock_stop.assert_awaited_once()
        mock_hangup.assert_awaited_once()
        assert "RECOVERING" in _phases_broadcast(mock_bc)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("phase", [Phase.HEALTHY, Phase.DIAGNOSING, Phase.RECOVERING])
    async def test_ignored_outside_the_calling_phase(self, phase: Phase) -> None:
        from websocket_server import handle_client_message

        demo_state.phase = phase
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock), \
             patch("voice.voice_router.voice_router.stop_session", new_callable=AsyncMock) as mock_stop, \
             patch("websocket_server._cancel_inflight_twilio_call", new_callable=AsyncMock) as mock_hangup:
            await handle_client_message(json.dumps({"type": "end_call", "payload": {}}))

        assert demo_state.phase == phase
        mock_stop.assert_not_awaited()
        mock_hangup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_hangs_up_before_dropping_the_voice_session(self) -> None:
        """stop_session() clears voice_router.twilio_session, and the REST hangup needs
        its call_sid — so the hangup has to happen first or the phone keeps ringing."""
        from websocket_server import handle_client_message

        order: list[str] = []
        demo_state.phase = Phase.CALLING
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock), \
             patch("voice.voice_router.voice_router.stop_session", new_callable=AsyncMock,
                   side_effect=lambda: order.append("stop_session")), \
             patch("websocket_server._cancel_inflight_twilio_call", new_callable=AsyncMock,
                   side_effect=lambda: order.append("hangup")):
            await handle_client_message(json.dumps({"type": "end_call", "payload": {}}))

        assert order == ["hangup", "stop_session"]

    @pytest.mark.asyncio
    async def test_phase_moves_off_calling_before_the_session_ends(self) -> None:
        """The session-end callback advances the phase when it still reads CALLING.
        Setting RECOVERING first keeps the run from skipping straight to RESOLVED."""
        from websocket_server import handle_client_message

        seen: list[Phase] = []
        demo_state.phase = Phase.CALLING
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock), \
             patch("voice.voice_router.voice_router.stop_session", new_callable=AsyncMock,
                   side_effect=lambda: seen.append(demo_state.phase)), \
             patch("websocket_server._cancel_inflight_twilio_call", new_callable=AsyncMock):
            await handle_client_message(json.dumps({"type": "end_call", "payload": {}}))

        assert seen == [Phase.RECOVERING]
        assert demo_state.phase == Phase.RECOVERING


class TestVoiceHardCeiling:
    def test_bounds_dead_air_to_two_minutes(self) -> None:
        """Automatic backstop for when nobody is at the console to press END CALL."""
        from demo_controller import VOICE_HARD_CEILING

        assert VOICE_HARD_CEILING <= 120.0
