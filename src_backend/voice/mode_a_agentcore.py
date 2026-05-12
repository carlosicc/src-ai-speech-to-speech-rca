"""Mode A: AgentCore BidiAgent + Twilio voice session.

Places an outbound call via Twilio, then bridges the Twilio Media Stream
audio through to an AgentCore BidiAgent Runtime via SigV4-signed WebSocket.

The BidiAgent handles Nova Sonic conversation + tools internally.
Audio flow:
  Phone → Twilio Media Stream (mulaw 8kHz) → resample to PCM 16kHz
  → AgentCore BidiAgent WebSocket (bidi_audio_input)
  → BidiAgent processes with Nova Sonic + tools
  → bidi_audio_output (PCM 16kHz) → resample to mulaw 8kHz
  → Twilio Media Stream → phone speaker
"""

import asyncio
import base64
import json
import logging
import struct
from typing import Any, Callable, Coroutine

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session as BotocoreSession

from shared import config as shared_config
from shared.state import demo_state
from voice.audio_converter import mulaw_decode, mulaw_encode, resample_8k_to_16k, resample_16k_to_8k
from voice.twilio_handler import place_outbound_call

logger = logging.getLogger(__name__)


def _build_signed_ws_url(runtime_arn: str, region: str) -> str:
    """Build a SigV4 presigned WebSocket URL for AgentCore Runtime."""
    from urllib.parse import quote, urlencode
    from datetime import datetime, timezone
    import hashlib
    import hmac

    host = f"bedrock-agentcore.{region}.amazonaws.com"
    encoded_arn = quote(runtime_arn, safe="")
    path = f"/runtimes/{encoded_arn}/ws"

    session = BotocoreSession()
    credentials = session.get_credentials().get_frozen_credentials()

    now = datetime.now(timezone.utc)
    datestamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")

    service = "bedrock-agentcore"
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"

    query_params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{credentials.access_key}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": "300",
        "X-Amz-SignedHeaders": "host",
    }
    if credentials.token:
        query_params["X-Amz-Security-Token"] = credentials.token

    canonical_querystring = urlencode(sorted(query_params.items()))
    canonical_headers = f"host:{host}\n"
    signed_headers = "host"
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_request = f"GET\n{path}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"

    def sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    signing_key = sign(
        sign(
            sign(
                sign(f"AWS4{credentials.secret_key}".encode("utf-8"), datestamp),
                region,
            ),
            service,
        ),
        "aws4_request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    final_qs = f"{canonical_querystring}&X-Amz-Signature={signature}"
    return f"wss://{host}{path}?{final_qs}"


class AgentCoreVoiceSession:
    """Mode A voice session: Twilio phone call bridged to AgentCore BidiAgent.

    Lifecycle:
    1. start() places outbound call via Twilio + connects WS to AgentCore
    2. Twilio connects Media Stream WebSocket to /twilio/media-stream
    3. Audio is bridged: Twilio mulaw ↔ PCM 16kHz ↔ AgentCore bidi events
    4. Session ends when call hangs up or timeout reached
    """

    def __init__(
        self,
        on_transcript: Callable[[str, str], Coroutine[Any, Any, None]],
        on_session_end: Callable[[], Coroutine[Any, Any, None]],
        media_stream_url: str = "",
    ) -> None:
        self._on_transcript = on_transcript
        self._on_session_end = on_session_end
        self._media_stream_url = media_stream_url
        self._call_sid: str | None = None
        self._agentcore_ws: Any = None
        self._twilio_ws: Any = None
        self._twilio_stream_sid: str = ""
        self._active = False
        self._receive_task: asyncio.Task | None = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def call_sid(self) -> str | None:
        return self._call_sid

    async def start(self) -> None:
        """Place outbound call and connect to AgentCore."""
        self._active = True
        phone_number = demo_state.phone_number

        if not shared_config.AGENTCORE_RUNTIME_ARN:
            logger.error("Mode A: AGENTCORE_RUNTIME_ARN not configured, cannot start")
            self._active = False
            await self._on_session_end()
            return

        logger.info(f"Mode A: placing outbound call to {phone_number}")
        self._call_sid = await place_outbound_call(phone_number, self._media_stream_url)

        if not self._call_sid:
            logger.error("Mode A: failed to place outbound call")
            self._active = False
            await self._on_session_end()
            return

        try:
            await self._connect_agentcore()
        except Exception as e:
            logger.error(f"Mode A: failed to connect to AgentCore: {e}")
            self._active = False
            await self._on_session_end()

    async def _connect_agentcore(self) -> None:
        """Establish SigV4-signed WebSocket to AgentCore Runtime."""
        import websockets

        ws_url = _build_signed_ws_url(shared_config.AGENTCORE_RUNTIME_ARN, shared_config.AGENTCORE_REGION)
        logger.info(f"Mode A: connecting to AgentCore WebSocket")
        self._agentcore_ws = await websockets.connect(ws_url)
        logger.info("Mode A: AgentCore WebSocket connected")

        self._receive_task = asyncio.create_task(self._receive_from_agentcore())

        await self._agentcore_ws.send(json.dumps({
            "type": "bidi_session_start",
            "context": {"call_type": "outbound", "reason": "incident_response"},
        }))

    async def _receive_from_agentcore(self) -> None:
        """Process messages from AgentCore BidiAgent."""
        try:
            async for message in self._agentcore_ws:
                if not self._active:
                    break
                data = json.loads(message)
                event_type = data.get("type", "")

                if event_type in ("bidi_audio_output", "bidi_audio_stream"):
                    audio_b64 = data.get("audio", "")
                    if audio_b64 and self._twilio_ws and self._twilio_stream_sid:
                        pcm_16k = base64.b64decode(audio_b64)
                        pcm_8k = resample_16k_to_8k(pcm_16k)
                        mulaw = mulaw_encode(pcm_8k)
                        mulaw_b64 = base64.b64encode(mulaw).decode("ascii")
                        media_msg = {
                            "event": "media",
                            "streamSid": self._twilio_stream_sid,
                            "media": {"payload": mulaw_b64},
                        }
                        try:
                            await self._twilio_ws.send_text(json.dumps(media_msg))
                        except Exception:
                            pass

                elif event_type in ("bidi_text_output", "bidi_transcript_stream"):
                    text = data.get("text", "")
                    role = data.get("role", "ASSISTANT")
                    if text:
                        speaker = "human" if role.upper() == "USER" else "agent"
                        await self._on_transcript(text, speaker)

                elif event_type == "bidi_tool_call":
                    tool_name = data.get("tool_name", "")
                    await self._on_transcript(f"[Executing: {tool_name}]", "agent")

                elif event_type == "error":
                    logger.error(f"AgentCore error: {data.get('message', '')}")

        except Exception as e:
            if self._active:
                logger.error(f"Mode A: AgentCore receive error: {e}")
        finally:
            if self._active:
                self._active = False
                await self._on_session_end()

    async def handle_twilio_media(self, websocket: Any, stream_sid: str, call_sid: str) -> None:
        """Attach Twilio Media Stream and begin bridging audio."""
        self._twilio_ws = websocket
        self._twilio_stream_sid = stream_sid
        logger.info(f"Mode A: Twilio Media Stream attached (streamSid={stream_sid})")

    async def receive_twilio_audio(self, mulaw_payload: str) -> None:
        """Receive mulaw audio from Twilio and forward to AgentCore."""
        if not self._active or not self._agentcore_ws:
            return
        mulaw_bytes = base64.b64decode(mulaw_payload)
        pcm_8k = mulaw_decode(mulaw_bytes)
        pcm_16k = resample_8k_to_16k(pcm_8k)
        pcm_b64 = base64.b64encode(pcm_16k).decode("ascii")

        try:
            await self._agentcore_ws.send(json.dumps({
                "type": "bidi_audio_input",
                "audio": pcm_b64,
                "format": "pcm",
                "sample_rate": 16000,
                "channels": 1,
            }))
        except Exception as e:
            logger.warning(f"Mode A: failed to send audio to AgentCore: {e}")

    async def stop(self) -> None:
        """Stop the session and clean up."""
        if not self._active:
            return
        self._active = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._agentcore_ws:
            try:
                await self._agentcore_ws.close()
            except Exception:
                pass
            self._agentcore_ws = None

        logger.info("Mode A: session stopped")
