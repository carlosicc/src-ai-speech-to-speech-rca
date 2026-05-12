"""Tests for Phase 4 UX fixes (7 issues from 2026-05-12 spec)."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend"))


class TestIssue1_MicDisabledInModeB:
    """Issue 1: audio_input should be ignored when voice_mode != mode_c."""

    def test_audio_input_ignored_in_mode_b(self):
        from shared.state import demo_state, Phase
        from websocket_server import handle_client_message

        demo_state.phase = Phase.CALLING
        demo_state.voice_mode = "mode_b"

        with patch("voice.voice_router.voice_router") as mock_router:
            mock_router.active = False
            asyncio.run(handle_client_message(json.dumps({
                "type": "audio_input",
                "payload": {"audio": "dGVzdA=="},
            })))
            mock_router.receive_audio.assert_not_called()

        demo_state.reset()
        demo_state.voice_mode = "mode_c"

    def test_audio_input_ignored_in_mode_a(self):
        from shared.state import demo_state, Phase
        from websocket_server import handle_client_message

        demo_state.phase = Phase.CALLING
        demo_state.voice_mode = "mode_a"

        with patch("voice.voice_router.voice_router") as mock_router:
            mock_router.active = False
            asyncio.run(handle_client_message(json.dumps({
                "type": "audio_input",
                "payload": {"audio": "dGVzdA=="},
            })))
            mock_router.receive_audio.assert_not_called()

        demo_state.reset()
        demo_state.voice_mode = "mode_c"

    def test_audio_input_accepted_in_mode_c(self):
        from shared.state import demo_state, Phase
        from websocket_server import handle_client_message

        demo_state.phase = Phase.CALLING
        demo_state.voice_mode = "mode_c"

        with patch("websocket_server._start_voice_session", new_callable=AsyncMock) as mock_start:
            with patch("voice.voice_router.voice_router") as mock_router:
                mock_router.active = False
                mock_router.receive_audio = AsyncMock()
                asyncio.run(handle_client_message(json.dumps({
                    "type": "audio_input",
                    "payload": {"audio": "dGVzdA=="},
                })))
                mock_start.assert_called_once()

        demo_state.reset()


class TestIssue2_AudioInputBypassesSafety:
    """Issue 2: audio_input must not start voice session in non-CALLING phase."""

    def test_audio_input_ignored_not_calling(self):
        from shared.state import demo_state, Phase
        from websocket_server import handle_client_message

        demo_state.phase = Phase.HEALTHY
        demo_state.voice_mode = "mode_c"

        with patch("voice.voice_router.voice_router") as mock_router:
            mock_router.active = False
            asyncio.run(handle_client_message(json.dumps({
                "type": "audio_input",
                "payload": {"audio": "dGVzdA=="},
            })))
            mock_router.receive_audio.assert_not_called()


class TestIssue3_TwilioCallingTimeout:
    """Issue 3: Extended timeout for Twilio and cancel on reset."""

    def test_twilio_calling_timeout_config(self):
        from shared.config import TWILIO_CALLING_TIMEOUT, VOICE_SESSION_TIMEOUT
        assert TWILIO_CALLING_TIMEOUT == 45
        assert VOICE_SESSION_TIMEOUT == 90
        assert TWILIO_CALLING_TIMEOUT < VOICE_SESSION_TIMEOUT

    def test_reset_cancels_voice_session(self):
        from shared.state import demo_state, Phase
        from websocket_server import handle_client_message

        demo_state.phase = Phase.CALLING

        with patch("websocket_server._cancel_inflight_twilio_call", new_callable=AsyncMock) as mock_cancel:
            with patch("voice.voice_router.voice_router") as mock_router:
                mock_router.stop_session = AsyncMock()
                with patch("websocket_server.manager") as mock_manager:
                    mock_manager.broadcast = AsyncMock()
                    asyncio.run(handle_client_message(json.dumps({
                        "type": "reset_demo",
                        "payload": {},
                    })))
                    mock_router.stop_session.assert_called_once()
                    mock_cancel.assert_called_once()

        demo_state.reset()

    def test_cancel_inflight_twilio_no_session(self):
        from websocket_server import _cancel_inflight_twilio_call

        with patch("voice.voice_router.voice_router") as mock_router:
            mock_router.twilio_session = None
            asyncio.run(_cancel_inflight_twilio_call())

    def test_cancel_inflight_twilio_with_call_sid(self):
        from websocket_server import _cancel_inflight_twilio_call

        mock_session = MagicMock()
        mock_session.call_sid = "CA_test123"

        mock_client = MagicMock()
        mock_call = MagicMock()
        mock_client.calls.return_value = mock_call

        with patch("voice.voice_router.voice_router") as mock_router:
            mock_router.twilio_session = mock_session
            with patch.dict("os.environ", {
                "TWILIO_ACCOUNT_SID": "AC_test",
                "TWILIO_AUTH_TOKEN": "tok_test",
                "TWILIO_FROM_NUMBER": "+15551234567",
            }):
                with patch("twilio.rest.Client", return_value=mock_client):
                    asyncio.run(_cancel_inflight_twilio_call())
                    mock_client.calls.assert_called_once_with("CA_test123")


class TestIssue4_ReducedLatency:
    """Issue 4: Shorter Polly intro and immediate greeting prompt."""

    def test_twiml_shorter_intro(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/twilio/outbound-call", headers={"host": "example.com"})
        assert response.status_code == 200
        assert "Connecting to AI Operations." in response.text
        assert "Please wait while we connect" not in response.text
        assert '<Pause' not in response.text

    def test_nova_sonic_prompt_immediate_greeting(self):
        from voice.nova_sonic_client import VOICE_AGENT_SYSTEM_PROMPT
        assert "Start speaking IMMEDIATELY" in VOICE_AGENT_SYSTEM_PROMPT
        assert "do NOT wait" in VOICE_AGENT_SYSTEM_PROMPT


class TestIssue5_ModelId:
    """Issue 5: BEDROCK_MODEL_ID default is the full model ID."""

    def test_default_model_id_is_full(self):
        from shared.config import BEDROCK_MODEL_ID
        assert "v1:0" in BEDROCK_MODEL_ID or "v1" in BEDROCK_MODEL_ID
        assert BEDROCK_MODEL_ID == "eu.anthropic.claude-sonnet-4-6-20250514-v1:0"

    def test_cdk_model_id_matches(self):
        import json
        cdk_path = Path(__file__).parent.parent.parent / "cdk.json"
        with open(cdk_path) as f:
            cdk = json.load(f)
        model_id = cdk["context"]["dev01"]["bedrock"]["models"]["standard"]["model_id"]
        assert model_id == "eu.anthropic.claude-sonnet-4-6-20250514-v1:0"


class TestIssue6_VoiceModeState:
    """Issue 6: voice_mode included in system_status broadcast."""

    def test_system_status_includes_voice_mode(self):
        from shared.state import demo_state
        from websocket_server import build_system_status

        demo_state.voice_mode = "mode_b"
        status = build_system_status(demo_state)
        assert status["payload"]["voice_mode"] == "mode_b"
        demo_state.voice_mode = "mode_c"

    def test_set_voice_mode_message(self):
        from shared.state import demo_state
        from websocket_server import handle_client_message

        asyncio.run(handle_client_message(json.dumps({
            "type": "set_voice_mode",
            "payload": {"mode": "mode_b"},
        })))
        assert demo_state.voice_mode == "mode_b"

        asyncio.run(handle_client_message(json.dumps({
            "type": "set_voice_mode",
            "payload": {"mode": "mode_c"},
        })))
        assert demo_state.voice_mode == "mode_c"


class TestIssue7_Tooltips:
    """Issue 7: Verify the tooltip content exists in DevPanel.tsx source."""

    def test_devpanel_has_tooltips(self):
        devpanel_path = Path(__file__).parent.parent.parent / "src_frontend" / "app" / "src" / "components" / "DevPanel.tsx"
        content = devpanel_path.read_text()
        assert 'title="Stop current incident, return to HEALTHY"' in content
        assert 'title="Auto-trigger incidents every 3min for booth passersby"' in content
        assert 'title="Send phone number to backend for Twilio calls"' in content
        assert 'title="Activate browser microphone for voice conversation (Mode C only)"' in content

    def test_devpanel_voice_mode_tooltips(self):
        devpanel_path = Path(__file__).parent.parent.parent / "src_frontend" / "app" / "src" / "components" / "DevPanel.tsx"
        content = devpanel_path.read_text()
        assert "AgentCore + Twilio" in content
        assert "Bedrock + Twilio" in content
        assert "Bedrock + Browser" in content

    def test_devpanel_mic_disabled_for_non_mode_c(self):
        devpanel_path = Path(__file__).parent.parent.parent / "src_frontend" / "app" / "src" / "components" / "DevPanel.tsx"
        content = devpanel_path.read_text()
        assert 'voiceMode !== "mode_c"' in content
