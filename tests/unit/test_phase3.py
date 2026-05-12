import asyncio
import base64
import json
import struct
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from shared.state import DemoState, Phase, demo_state
from voice.voice_tools import TOOL_SPECS, execute_tool, _authenticate_user, _check_service_health
from voice.mode_c_browser import resample_16k_to_24k, BrowserVoiceSession
from voice.voice_router import VoiceRouter


@pytest.fixture(autouse=True)
def reset_state():
    demo_state.reset()
    demo_state.auto_advance = True
    demo_state.voice_mode = "mode_c"
    demo_state.phone_number = "+44XXXXXXXXXX"
    yield
    demo_state.reset()


class TestVoiceTools:
    def test_tool_specs_structure(self):
        assert len(TOOL_SPECS) == 3
        names = {t["toolSpec"]["name"] for t in TOOL_SPECS}
        assert names == {"authenticate_user", "restart_database", "check_service_health"}

    def test_tool_specs_have_valid_json_schemas(self):
        for spec in TOOL_SPECS:
            schema_str = spec["toolSpec"]["inputSchema"]["json"]
            schema = json.loads(schema_str)
            assert "type" in schema
            assert schema["type"] == "object"
            assert "properties" in schema

    def test_authenticate_user_correct_passphrase(self):
        result = _authenticate_user("REDACTED_PASSPHRASE")
        assert result["status"] == "authenticated"

    def test_authenticate_user_case_insensitive(self):
        result = _authenticate_user("Aurora Sunrise")
        assert result["status"] == "authenticated"

    def test_authenticate_user_with_surrounding_text(self):
        result = _authenticate_user("my passphrase is REDACTED_PASSPHRASE okay")
        assert result["status"] == "authenticated"

    def test_authenticate_user_wrong_passphrase(self):
        result = _authenticate_user("wrong passphrase")
        assert result["status"] == "failed"

    def test_authenticate_user_empty_passphrase(self):
        result = _authenticate_user("")
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_restart_database_during_calling(self):
        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.CALLING
        result = await execute_tool("restart_database", {"service": "aurora-db"})
        assert result["status"] == "success"
        assert demo_state.phase == Phase.RECOVERING

    @pytest.mark.asyncio
    async def test_restart_database_not_calling(self):
        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.DIAGNOSING
        result = await execute_tool("restart_database", {"service": "aurora-db"})
        assert result["status"] == "success"
        assert demo_state.phase == Phase.DIAGNOSING

    def test_check_service_health_during_incident(self):
        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.CALLING
        result = _check_service_health("aurora-db")
        assert result["status"] == "CRITICAL"
        assert result["cpu_percent"] == 98
        assert result["iops"] == 0

    def test_check_service_health_healthy(self):
        result = _check_service_health("aurora-db")
        assert result["status"] == "HEALTHY"
        assert result["cpu_percent"] == 35

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self):
        result = await execute_tool("nonexistent_tool", {})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_execute_tool_authenticate(self):
        result = await execute_tool("authenticate_user", {"passphrase": "REDACTED_PASSPHRASE"})
        assert result["status"] == "authenticated"

    @pytest.mark.asyncio
    async def test_execute_tool_check_health(self):
        result = await execute_tool("check_service_health", {"service": "lambda"})
        assert result["status"] == "HEALTHY"


class TestResample:
    def test_resample_basic(self):
        num_samples = 1600
        pcm_16k = struct.pack(f"<{num_samples}h", *([1000] * num_samples))
        pcm_24k = resample_16k_to_24k(pcm_16k)
        expected_samples = int(num_samples * (24000 / 16000))
        actual_samples = len(pcm_24k) // 2
        assert abs(actual_samples - expected_samples) <= 1

    def test_resample_preserves_silence(self):
        num_samples = 1600
        pcm_16k = struct.pack(f"<{num_samples}h", *([0] * num_samples))
        pcm_24k = resample_16k_to_24k(pcm_16k)
        samples_out = struct.unpack(f"<{len(pcm_24k) // 2}h", pcm_24k)
        assert all(s == 0 for s in samples_out)

    def test_resample_small_input(self):
        pcm_16k = struct.pack("<1h", 500)
        result = resample_16k_to_24k(pcm_16k)
        assert len(result) == 2

    def test_resample_signal_integrity(self):
        num_samples = 160
        sine_samples = [int(10000 * (i / num_samples)) for i in range(num_samples)]
        pcm_16k = struct.pack(f"<{num_samples}h", *sine_samples)
        pcm_24k = resample_16k_to_24k(pcm_16k)
        samples_out = struct.unpack(f"<{len(pcm_24k) // 2}h", pcm_24k)
        assert samples_out[0] == 0
        assert samples_out[-1] > 9000


class TestBrowserVoiceSession:
    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        session = BrowserVoiceSession(
            on_audio_output=on_audio,
            on_transcript=on_transcript,
            on_session_end=on_end,
        )
        assert not session.active

    @pytest.mark.asyncio
    async def test_session_start_creates_nova_session(self):
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        session = BrowserVoiceSession(
            on_audio_output=on_audio,
            on_transcript=on_transcript,
            on_session_end=on_end,
        )

        with patch("voice.mode_c_browser.NovaSonicSession") as mock_nova:
            mock_instance = AsyncMock()
            mock_instance.active = True
            mock_nova.return_value = mock_instance
            await session.start()
            assert session.active
            mock_instance.start.assert_called_once()
            await session.stop()

    @pytest.mark.asyncio
    async def test_receive_audio_resamples_and_forwards(self):
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        session = BrowserVoiceSession(
            on_audio_output=on_audio,
            on_transcript=on_transcript,
            on_session_end=on_end,
        )

        with patch("voice.mode_c_browser.NovaSonicSession") as mock_nova:
            mock_instance = AsyncMock()
            mock_instance.active = True
            mock_nova.return_value = mock_instance
            await session.start()

            pcm_16k = struct.pack("<160h", *([500] * 160))
            pcm_b64 = base64.b64encode(pcm_16k).decode("ascii")
            await session.receive_audio(pcm_b64)

            mock_instance.send_audio.assert_called_once()
            sent_b64 = mock_instance.send_audio.call_args[0][0]
            sent_bytes = base64.b64decode(sent_b64)
            expected_samples = int(160 * (24000 / 16000))
            actual_samples = len(sent_bytes) // 2
            assert abs(actual_samples - expected_samples) <= 1

            await session.stop()


class TestVoiceRouter:
    @pytest.mark.asyncio
    async def test_router_not_active_initially(self):
        router = VoiceRouter()
        assert not router.active

    @pytest.mark.asyncio
    async def test_router_starts_mode_c(self):
        router = VoiceRouter()
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        demo_state.voice_mode = "mode_c"

        with patch("voice.voice_router.BrowserVoiceSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.active = True
            mock_session_cls.return_value = mock_session

            await router.start_session(on_audio, on_transcript, on_end)
            mock_session.start.assert_called_once()
            assert router.active

            await router.stop_session()
            mock_session.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_router_receive_audio_forwards(self):
        router = VoiceRouter()
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        demo_state.voice_mode = "mode_c"

        with patch("voice.voice_router.BrowserVoiceSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.active = True
            mock_session_cls.return_value = mock_session

            await router.start_session(on_audio, on_transcript, on_end)
            await router.receive_audio("dGVzdA==")
            mock_session.receive_audio.assert_called_once_with("dGVzdA==")

            await router.stop_session()

    @pytest.mark.asyncio
    async def test_router_mode_b_falls_back_to_mode_c(self):
        router = VoiceRouter()
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        demo_state.voice_mode = "mode_b"

        with patch("voice.voice_router.BrowserVoiceSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.active = True
            mock_session_cls.return_value = mock_session

            await router.start_session(on_audio, on_transcript, on_end)
            mock_session.start.assert_called_once()
            await router.stop_session()


class TestAudioInputWebSocket:
    @pytest.mark.asyncio
    async def test_audio_input_routes_to_voice_router(self):
        from websocket_server import handle_client_message
        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.CALLING

        with patch("voice.voice_router.voice_router") as mock_router:
            mock_router.receive_audio = AsyncMock()
            msg = json.dumps({"type": "audio_input", "payload": {"audio": "dGVzdA=="}})
            await handle_client_message(msg)
            mock_router.receive_audio.assert_called_once_with("dGVzdA==")

    @pytest.mark.asyncio
    async def test_audio_input_ignored_when_not_calling(self):
        from websocket_server import handle_client_message
        demo_state.phase = Phase.HEALTHY

        with patch("voice.voice_router.voice_router") as mock_router:
            mock_router.receive_audio = AsyncMock()
            msg = json.dumps({"type": "audio_input", "payload": {"audio": "dGVzdA=="}})
            await handle_client_message(msg)
            mock_router.receive_audio.assert_not_called()
