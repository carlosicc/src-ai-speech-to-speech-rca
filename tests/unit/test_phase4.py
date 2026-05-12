"""Tests for Phase 4: Twilio Integration + Voice Mode B."""

import asyncio
import base64
import struct
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src_backend"))


class TestAudioConverter:
    """Test mulaw ↔ PCM conversion and resampling."""

    def test_mulaw_decode_silence(self):
        from voice.audio_converter import mulaw_decode
        silence_mulaw = bytes([0xFF] * 10)
        pcm = mulaw_decode(silence_mulaw)
        assert len(pcm) == 20
        samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
        for s in samples:
            assert abs(s) < 10

    def test_mulaw_encode_silence(self):
        from voice.audio_converter import mulaw_encode
        silence_pcm = struct.pack("<10h", *([0] * 10))
        mulaw = mulaw_encode(silence_pcm)
        assert len(mulaw) == 10

    def test_mulaw_roundtrip(self):
        from voice.audio_converter import mulaw_decode, mulaw_encode
        original_samples = [0, 1000, -1000, 5000, -5000, 32000, -32000, 100, -100, 0]
        pcm = struct.pack(f"<{len(original_samples)}h", *original_samples)
        mulaw = mulaw_encode(pcm)
        decoded = mulaw_decode(mulaw)
        decoded_samples = struct.unpack(f"<{len(decoded) // 2}h", decoded)
        for orig, dec in zip(original_samples, decoded_samples):
            tolerance = max(500, abs(orig) * 0.25)
            assert abs(orig - dec) < tolerance, f"Mulaw roundtrip error too large: {orig} -> {dec}"

    def test_resample_8k_to_24k(self):
        from voice.audio_converter import resample_8k_to_24k
        samples_8k = struct.pack("<4h", 0, 100, 200, 300)
        pcm_24k = resample_8k_to_24k(samples_8k)
        num_out = len(pcm_24k) // 2
        assert num_out == 12

    def test_resample_24k_to_8k(self):
        from voice.audio_converter import resample_24k_to_8k
        samples_24k = struct.pack("<9h", *range(9))
        pcm_8k = resample_24k_to_8k(samples_24k)
        num_out = len(pcm_8k) // 2
        assert num_out == 3
        samples = struct.unpack(f"<{num_out}h", pcm_8k)
        assert samples == (0, 3, 6)

    def test_twilio_to_nova_pipeline(self):
        from voice.audio_converter import twilio_to_nova
        mulaw_data = bytes([0xFF, 0x7F, 0x80, 0x00] * 40)
        result = twilio_to_nova(mulaw_data)
        decoded = base64.b64decode(result)
        assert len(decoded) > len(mulaw_data) * 2

    def test_nova_to_twilio_pipeline(self):
        from voice.audio_converter import nova_to_twilio
        samples = [0, 500, -500, 1000] * 60
        pcm_24k = struct.pack(f"<{len(samples)}h", *samples)
        result = nova_to_twilio(pcm_24k)
        decoded = base64.b64decode(result)
        assert len(decoded) == len(samples) // 3


class TestTwilioHandler:
    """Test Twilio handler logic."""

    def test_place_outbound_call_no_credentials(self):
        from voice.twilio_handler import place_outbound_call
        with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": ""}, clear=False):
            with patch("shared.config.TWILIO_SECRET_ARN", ""):
                result = asyncio.run(place_outbound_call("+44XXXXXXXXXX", "wss://example.com/media-stream"))
                assert result is None

    def test_place_outbound_call_success(self):
        from voice.twilio_handler import place_outbound_call
        mock_call = MagicMock()
        mock_call.sid = "CA1234567890"
        mock_client = MagicMock()
        mock_client.calls.create.return_value = mock_call

        with patch.dict("os.environ", {
            "TWILIO_ACCOUNT_SID": "AC_test",
            "TWILIO_AUTH_TOKEN": "auth_test",
            "TWILIO_FROM_NUMBER": "+15551234567",
        }, clear=False):
            with patch("voice.twilio_handler._get_twilio_client", return_value=mock_client):
                result = asyncio.run(place_outbound_call("+44XXXXXXXXXX", "wss://example.com/media-stream"))
                assert result == "CA1234567890"
                mock_client.calls.create.assert_called_once()


class TestModeBSession:
    """Test Mode B voice session."""

    def test_session_start_no_url(self):
        from voice.mode_b_direct_twilio import TwilioVoiceSession
        on_transcript = AsyncMock()
        on_session_end = AsyncMock()
        session = TwilioVoiceSession(
            on_transcript=on_transcript,
            on_session_end=on_session_end,
            media_stream_url="",
        )
        assert not session.active

    def test_session_start_calls_twilio(self):
        from voice.mode_b_direct_twilio import TwilioVoiceSession
        on_transcript = AsyncMock()
        on_session_end = AsyncMock()
        session = TwilioVoiceSession(
            on_transcript=on_transcript,
            on_session_end=on_session_end,
            media_stream_url="wss://example.com/twilio/media-stream",
        )

        with patch("voice.mode_b_direct_twilio.place_outbound_call", new_callable=AsyncMock) as mock_place:
            mock_place.return_value = "CA_test_sid"
            asyncio.run(session.start())
            assert session.active
            assert session.call_sid == "CA_test_sid"
            mock_place.assert_called_once()

    def test_session_start_failure(self):
        from voice.mode_b_direct_twilio import TwilioVoiceSession
        on_transcript = AsyncMock()
        on_session_end = AsyncMock()
        session = TwilioVoiceSession(
            on_transcript=on_transcript,
            on_session_end=on_session_end,
            media_stream_url="wss://example.com/twilio/media-stream",
        )

        with patch("voice.mode_b_direct_twilio.place_outbound_call", new_callable=AsyncMock) as mock_place:
            mock_place.return_value = None
            asyncio.run(session.start())
            assert not session.active


class TestVoiceRouterModeB:
    """Test voice router mode B integration."""

    def test_mode_b_with_url(self):
        from voice.voice_router import VoiceRouter
        from shared.state import demo_state

        router = VoiceRouter()
        router.set_media_stream_url("wss://example.com/twilio/media-stream")

        demo_state.voice_mode = "mode_b"
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        with patch("voice.mode_b_direct_twilio.place_outbound_call", new_callable=AsyncMock) as mock_place:
            mock_place.return_value = "CA_test"
            asyncio.run(router.start_session(on_audio, on_transcript, on_end))
            assert router.twilio_session is not None
            assert router.twilio_session.active

        demo_state.voice_mode = "mode_c"

    def test_mode_b_fallback_no_url(self):
        from voice.voice_router import VoiceRouter
        from shared.state import demo_state

        router = VoiceRouter()
        demo_state.voice_mode = "mode_b"
        on_audio = AsyncMock()
        on_transcript = AsyncMock()
        on_end = AsyncMock()

        with patch("voice.mode_c_browser.NovaSonicSession") as mock_nova:
            mock_instance = AsyncMock()
            mock_nova.return_value = mock_instance
            asyncio.run(router.start_session(on_audio, on_transcript, on_end))
            assert router.twilio_session is None

        demo_state.voice_mode = "mode_c"


class TestConfig:
    """Test config loading for Twilio."""

    def test_load_twilio_from_env(self):
        from shared.config import load_twilio_credentials
        with patch.dict("os.environ", {
            "TWILIO_ACCOUNT_SID": "AC_env",
            "TWILIO_AUTH_TOKEN": "token_env",
            "TWILIO_FROM_NUMBER": "+15551111111",
        }, clear=False):
            sid, token, number = load_twilio_credentials()
            assert sid == "AC_env"
            assert token == "token_env"
            assert number == "+15551111111"

    def test_load_twilio_no_config(self):
        from shared.config import load_twilio_credentials
        with patch.dict("os.environ", {
            "TWILIO_ACCOUNT_SID": "",
            "TWILIO_AUTH_TOKEN": "",
            "TWILIO_FROM_NUMBER": "",
        }, clear=False):
            with patch("shared.config.TWILIO_SECRET_ARN", ""):
                sid, token, number = load_twilio_credentials()
                assert sid == ""
                assert token == ""


class TestMainEndpoints:
    """Test FastAPI endpoints."""

    def test_twilio_outbound_call_twiml(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.get("/twilio/outbound-call", headers={"host": "example.com"})
        assert response.status_code == 200
        assert "text/xml" in response.headers["content-type"]
        assert "<Stream" in response.text
        assert "example.com/twilio/media-stream" in response.text

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
