"""Tests for Phase 5: AgentCore + Voice Mode A."""

import asyncio
import base64
import json
import struct
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend"))


class TestAudioConverter16k:
    """Test 8kHz ↔ 16kHz resampling for Mode A (AgentCore uses 16kHz)."""

    def test_resample_8k_to_16k(self):
        from voice.audio_converter import resample_8k_to_16k
        samples_8k = struct.pack("<4h", 0, 100, 200, 300)
        pcm_16k = resample_8k_to_16k(samples_8k)
        num_out = len(pcm_16k) // 2
        assert num_out == 8  # 4 input * 2 = 8 output

    def test_resample_16k_to_8k(self):
        from voice.audio_converter import resample_16k_to_8k
        samples_16k = struct.pack("<8h", 0, 50, 100, 150, 200, 250, 300, 350)
        pcm_8k = resample_16k_to_8k(samples_16k)
        num_out = len(pcm_8k) // 2
        assert num_out == 4  # picks every 2nd
        samples = struct.unpack(f"<{num_out}h", pcm_8k)
        assert samples == (0, 100, 200, 300)

    def test_roundtrip_8k_16k_8k(self):
        from voice.audio_converter import resample_8k_to_16k, resample_16k_to_8k
        original = struct.pack("<4h", 100, 200, 300, 400)
        pcm_16k = resample_8k_to_16k(original)
        pcm_8k = resample_16k_to_8k(pcm_16k)
        num_out = len(pcm_8k) // 2
        assert num_out == 4
        samples = struct.unpack(f"<{num_out}h", pcm_8k)
        # Roundtrip should preserve original samples (since we pick every 2nd)
        assert samples == (100, 200, 300, 400)


class TestConfig:
    """Test AgentCore config loading."""

    def test_agentcore_config_defaults(self):
        from shared.config import AGENTCORE_RUNTIME_ARN, AGENTCORE_REGION
        # Defaults are empty/us-east-1 when env vars not set
        assert AGENTCORE_REGION == "us-east-1"
        # ARN is empty by default (Mode A won't start without it)
        assert isinstance(AGENTCORE_RUNTIME_ARN, str)


class TestVoiceRouterModeA:
    """Test voice router Mode A dispatch."""

    def test_mode_a_no_arn_falls_back(self):
        from voice.voice_router import VoiceRouter
        from shared.state import demo_state

        router = VoiceRouter()
        demo_state.voice_mode = "mode_a"
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        with patch("shared.config.AGENTCORE_RUNTIME_ARN", ""):
            with patch("voice.mode_c_browser.NovaSonicSession") as mock_nova:
                mock_instance = AsyncMock()
                mock_nova.return_value = mock_instance
                asyncio.run(router.start_session(on_audio, on_transcript, on_end))
                # Falls back to browser mode since no ARN and no media_stream_url
                assert router.agentcore_session is None

        demo_state.voice_mode = "mode_c"

    def test_mode_a_with_arn_creates_session(self):
        from voice.voice_router import VoiceRouter
        from shared.state import demo_state

        router = VoiceRouter()
        router.set_media_stream_url("wss://example.com/twilio/media-stream")
        demo_state.voice_mode = "mode_a"
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        import shared.config as _cfg
        original = _cfg.AGENTCORE_RUNTIME_ARN
        _cfg.AGENTCORE_RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:123456:runtime/test"
        try:
            with patch("voice.mode_a_agentcore.place_outbound_call", new_callable=AsyncMock) as mock_place:
                mock_place.return_value = "CA_test"
                with patch("voice.mode_a_agentcore._build_signed_ws_url", return_value="wss://fake"):
                    with patch("websockets.connect", new_callable=AsyncMock) as mock_ws_connect:
                        mock_ws = AsyncMock()
                        mock_ws_connect.return_value = mock_ws
                        asyncio.run(router.start_session(on_audio, on_transcript, on_end))
                        assert router.agentcore_session is not None
                        # Session was created and call was placed
                        mock_place.assert_called_once()
                        mock_ws_connect.assert_called_once_with("wss://fake")
        finally:
            _cfg.AGENTCORE_RUNTIME_ARN = original

        demo_state.voice_mode = "mode_c"


class TestAgentCoreVoiceSession:
    """Test Mode A AgentCoreVoiceSession."""

    def test_session_no_arn(self):
        from voice.mode_a_agentcore import AgentCoreVoiceSession
        import shared.config as _cfg
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        original = _cfg.AGENTCORE_RUNTIME_ARN
        _cfg.AGENTCORE_RUNTIME_ARN = ""
        try:
            session = AgentCoreVoiceSession(
                on_transcript=on_transcript,
                on_session_end=on_end,
                media_stream_url="wss://example.com/twilio/media-stream",
            )
            asyncio.run(session.start())
            assert not session.active
            on_end.assert_called_once()
        finally:
            _cfg.AGENTCORE_RUNTIME_ARN = original

    def test_session_call_fails(self):
        from voice.mode_a_agentcore import AgentCoreVoiceSession
        import shared.config as _cfg
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        original = _cfg.AGENTCORE_RUNTIME_ARN
        _cfg.AGENTCORE_RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:123456:runtime/test"
        try:
            with patch("voice.mode_a_agentcore.place_outbound_call", new_callable=AsyncMock) as mock_place:
                mock_place.return_value = None
                session = AgentCoreVoiceSession(
                    on_transcript=on_transcript,
                    on_session_end=on_end,
                    media_stream_url="wss://example.com/twilio/media-stream",
                )
                asyncio.run(session.start())
                assert not session.active
                on_end.assert_called_once()
        finally:
            _cfg.AGENTCORE_RUNTIME_ARN = original

    def test_session_receives_audio(self):
        from voice.mode_a_agentcore import AgentCoreVoiceSession
        import shared.config as _cfg
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        original = _cfg.AGENTCORE_RUNTIME_ARN
        _cfg.AGENTCORE_RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:123456:runtime/test"
        try:
            with patch("voice.mode_a_agentcore.place_outbound_call", new_callable=AsyncMock) as mock_place:
                mock_place.return_value = "CA_test"
                with patch("voice.mode_a_agentcore._build_signed_ws_url", return_value="wss://fake"):
                    with patch("websockets.connect", new_callable=AsyncMock) as mock_ws_connect:
                        mock_ws = AsyncMock()
                        mock_ws.send = AsyncMock()
                        mock_ws_connect.return_value = mock_ws

                        session = AgentCoreVoiceSession(
                            on_transcript=on_transcript,
                            on_session_end=on_end,
                            media_stream_url="wss://example.com/twilio/media-stream",
                        )
                        asyncio.run(session.start())
                        # Force active since receive_task will finish quickly with mock
                        session._active = True

                        # Send mulaw audio to session
                        mulaw_data = base64.b64encode(bytes([0xFF] * 160)).decode()
                        asyncio.run(session.receive_twilio_audio(mulaw_data))
                        mock_ws.send.assert_called()
                        sent_data = json.loads(mock_ws.send.call_args[0][0])
                        assert sent_data["type"] == "bidi_audio_input"
                        assert sent_data["sample_rate"] == 16000
        finally:
            _cfg.AGENTCORE_RUNTIME_ARN = original


class TestAgentCoreAgent:
    """Test the standalone BidiAgent container code."""

    def test_tools_authenticate_success(self):
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend" / "voice" / "agentcore_agent"))
        from tools import authenticate_user
        result = authenticate_user(spoken_passphrase="REDACTED_PASSPHRASE")
        assert result["authenticated"] is True

    def test_tools_authenticate_failure(self):
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend" / "voice" / "agentcore_agent"))
        from tools import authenticate_user
        result = authenticate_user(spoken_passphrase="wrong passphrase")
        assert result["authenticated"] is False

    def test_tools_restart_database(self):
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend" / "voice" / "agentcore_agent"))
        from tools import restart_database
        result = restart_database(service="aurora-db")
        assert result["status"] == "restarted"
        assert result["service"] == "aurora-db"

    def test_tools_check_health(self):
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend" / "voice" / "agentcore_agent"))
        from tools import check_service_health
        result = check_service_health(service="aurora-db")
        assert result["status"] == "CRITICAL"
        assert result["cpu_percent"] == 98


class TestCdkAgentCoreStack:
    """Test CDK AgentCore stack synthesis."""

    def test_stack_synthesizes(self):
        import aws_cdk as cdk
        from aws_cdk.assertions import Template

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from src_infra.stack_infrastructure import InfrastructureStack
        from src_infra.stack_agentcore import AgentCoreStack

        app = cdk.App(context={
            "dev01": {
                "project_name": "rca",
                "region": "eu-west-1",
                "bedrock": {
                    "region": "eu-west-1",
                    "models": {
                        "voice": {"model_id": "amazon.nova-sonic-v1:0"},
                        "standard": {"model_id": "eu.anthropic.claude-sonnet-4-6"},
                    },
                },
            }
        })

        env = cdk.Environment(account="123456789012", region="eu-west-1")
        infra = InfrastructureStack(
            app, "TestInfra",
            env_name="dev01",
            env_context=app.node.try_get_context("dev01"),
            env=env,
        )
        stack = AgentCoreStack(
            app, "TestAgentCore",
            env_name="dev01",
            env_context=app.node.try_get_context("dev01"),
            infrastructure=infra,
            env=env,
        )

        template = Template.from_stack(stack)
        # Should have an IAM role for the runtime
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "rca-agentcore-role-dev01",
        })
