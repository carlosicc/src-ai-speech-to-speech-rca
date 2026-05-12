"""Twilio outbound call placement and Media Stream WebSocket handling.

Places outbound calls via Twilio REST API with TwiML that connects
a Media Stream WebSocket back to our server for bidirectional audio.
"""

import asyncio
import base64
import json
import logging
import struct
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from shared.config import load_twilio_credentials
from shared.state import demo_state
from voice.audio_converter import nova_to_twilio, twilio_to_nova
from voice.nova_sonic_client import NovaSonicSession

logger = logging.getLogger(__name__)


def _get_twilio_client() -> Any:
    """Lazy-load Twilio client with credentials from Secrets Manager."""
    account_sid, auth_token, _ = load_twilio_credentials()
    if not account_sid or not auth_token:
        raise ValueError("Twilio credentials not configured")
    from twilio.rest import Client
    return Client(account_sid, auth_token)


async def place_outbound_call(to_number: str, media_stream_url: str) -> str | None:
    """Place an outbound call via Twilio that connects a Media Stream to our WebSocket.

    Returns the call SID on success, None on failure.
    """
    account_sid, auth_token, from_number = load_twilio_credentials()
    if not all([account_sid, auth_token, from_number]):
        logger.error("Twilio credentials not configured")
        return None

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        '<Say language="en-US" voice="Polly.Matthew-Generative">'
        "Please wait while we connect your call to the AI Operations Center."
        "</Say>"
        '<Pause length="1"/>'
        "<Connect>"
        f'<Stream url="{media_stream_url}" />'
        "</Connect>"
        "</Response>"
    )

    try:
        client = _get_twilio_client()
        call = await asyncio.to_thread(
            client.calls.create,
            from_=from_number,
            to=to_number,
            twiml=twiml,
        )
        logger.info(f"Twilio outbound call placed: SID={call.sid} to={to_number}")
        return call.sid
    except Exception as e:
        logger.error(f"Failed to place Twilio call: {e}")
        return None


class TwilioMediaStreamHandler:
    """Handles a Twilio Media Stream WebSocket connection.

    Bridges audio between Twilio (mulaw 8kHz) and Nova Sonic (PCM 24kHz).
    """

    def __init__(
        self,
        websocket: WebSocket,
        on_transcript: Any,
        on_session_end: Any,
    ) -> None:
        self._ws = websocket
        self._on_transcript = on_transcript
        self._on_session_end = on_session_end
        self._stream_sid: str = ""
        self._call_sid: str = ""
        self._nova_session: NovaSonicSession | None = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def call_sid(self) -> str:
        return self._call_sid

    async def handle(self) -> None:
        """Process the Twilio Media Stream WebSocket lifecycle."""
        self._active = True
        try:
            while self._active:
                data = await self._ws.receive_text()
                message = json.loads(data)
                event_type = message.get("event", "")

                if event_type == "connected":
                    logger.info("Twilio Media Stream: connected")

                elif event_type == "start":
                    self._stream_sid = message.get("streamSid", "")
                    start_data = message.get("start", {})
                    self._call_sid = start_data.get("callSid", "")
                    logger.info(f"Twilio Media Stream started: streamSid={self._stream_sid}, callSid={self._call_sid}")
                    await self._start_nova_session()
                    await self._send_initial_audio()

                elif event_type == "media":
                    media = message.get("media", {})
                    payload = media.get("payload", "")
                    if payload and self._nova_session:
                        mulaw_bytes = base64.b64decode(payload)
                        pcm_24k_base64 = twilio_to_nova(mulaw_bytes)
                        await self._nova_session.send_audio(pcm_24k_base64)

                elif event_type == "stop":
                    logger.info("Twilio Media Stream: stop event received")
                    break

        except WebSocketDisconnect:
            logger.info("Twilio Media Stream: WebSocket disconnected")
        except Exception as e:
            logger.error(f"Twilio Media Stream error: {e}")
        finally:
            await self._cleanup()

    async def _start_nova_session(self) -> None:
        """Initialize the Nova Sonic session for this call."""
        self._nova_session = NovaSonicSession(
            on_audio_output=self._handle_nova_audio,
            on_transcript=self._on_transcript,
            on_session_end=self._handle_session_end,
        )
        await self._nova_session.start()
        logger.info("Nova Sonic session started for Twilio call")

    async def _send_initial_audio(self) -> None:
        """Send a short silence burst to Nova Sonic to trigger its greeting.

        Nova Sonic won't speak until it receives audio input.
        Send 500ms of silence (24kHz, 16-bit) to kickstart the conversation.
        """
        if not self._nova_session:
            return
        silence_samples = 12000  # 500ms at 24kHz
        silence_pcm = struct.pack(f"<{silence_samples}h", *([0] * silence_samples))
        silence_b64 = base64.b64encode(silence_pcm).decode("ascii")
        chunk_size = 4800  # 200ms chunks
        for i in range(0, silence_samples * 2, chunk_size * 2):
            chunk = silence_pcm[i:i + chunk_size * 2]
            chunk_b64 = base64.b64encode(chunk).decode("ascii")
            await self._nova_session.send_audio(chunk_b64)
        logger.info("Sent initial silence to Nova Sonic to trigger greeting")

    async def _handle_nova_audio(self, pcm_24k_bytes: bytes) -> None:
        """Convert Nova Sonic PCM output to mulaw and send to Twilio."""
        if not self._active or not self._stream_sid:
            return
        mulaw_base64 = nova_to_twilio(pcm_24k_bytes)
        media_message = {
            "event": "media",
            "streamSid": self._stream_sid,
            "media": {
                "payload": mulaw_base64,
            },
        }
        try:
            await self._ws.send_text(json.dumps(media_message))
        except Exception as e:
            logger.warning(f"Failed to send audio to Twilio: {e}")

    async def _handle_session_end(self) -> None:
        """Called when Nova Sonic session ends."""
        logger.info("Nova Sonic session ended for Twilio call")
        self._active = False
        await self._on_session_end()

    async def _cleanup(self) -> None:
        """Stop Nova Sonic session and mark inactive."""
        self._active = False
        if self._nova_session:
            await self._nova_session.stop()
            self._nova_session = None
        await self._on_session_end()

    async def send_clear(self) -> None:
        """Send a clear event to Twilio (for barge-in)."""
        if self._stream_sid:
            clear_message = {"event": "clear", "streamSid": self._stream_sid}
            try:
                await self._ws.send_text(json.dumps(clear_message))
            except Exception:
                pass
