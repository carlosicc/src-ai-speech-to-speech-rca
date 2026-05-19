"""Twilio outbound call placement and Media Stream WebSocket handling.

Places outbound calls via Twilio REST API with TwiML that connects
a Media Stream WebSocket back to our server for bidirectional audio.
"""

import asyncio
import base64
import json
import logging
import os
import struct
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from shared.config import load_twilio_credentials
from shared.state import demo_state
from voice.audio_converter import mulaw_decode, mulaw_encode
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
        "Connecting to AI Operations."
        "</Say>"
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

    Bridges audio between Twilio (mulaw 8kHz) and Nova Sonic (PCM 8kHz).
    """

    HELLO_PCM_PATH = os.path.join(os.path.dirname(__file__), "assets", "hello.pcm")

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
        """Process the Twilio Media Stream WebSocket lifecycle.

        Mirrors the official AWS sample's event ordering:
        - connected → create session + sessionStart + promptStart
        - start → systemPrompt + audioContentStart + hello.pcm
        - media → forward audio immediately (never blocked)
        """
        self._active = True
        try:
            while self._active:
                data = await self._ws.receive_text()
                message = json.loads(data)
                event_type = message.get("event", "")

                if event_type == "connected":
                    logger.info("Twilio Media Stream: connected")
                    await self._init_nova_session()

                elif event_type == "start":
                    self._stream_sid = message.get("streamSid", "")
                    start_data = message.get("start", {})
                    self._call_sid = start_data.get("callSid", "")
                    logger.info(f"Twilio Media Stream started: streamSid={self._stream_sid}, callSid={self._call_sid}")
                    await self._setup_nova_prompt()
                    await self._send_hello_audio()
                    asyncio.create_task(self._watchdog())

                elif event_type == "media":
                    self._media_count = getattr(self, "_media_count", 0) + 1
                    if self._media_count in (1, 10, 50, 100):
                        logger.info(f"Twilio media chunk #{self._media_count} received")
                    media = message.get("media", {})
                    payload = media.get("payload", "")
                    if payload and self._nova_session:
                        mulaw_bytes = base64.b64decode(payload)
                        pcm_8k = mulaw_decode(mulaw_bytes)
                        pcm_b64 = base64.b64encode(pcm_8k).decode("ascii")
                        await self._nova_session.send_audio(pcm_b64)

                elif event_type == "stop":
                    logger.info("Twilio Media Stream: stop event received")
                    break

        except WebSocketDisconnect:
            logger.info("Twilio Media Stream: WebSocket disconnected")
        except Exception as e:
            logger.error(f"Twilio Media Stream error: {e}")
        finally:
            await self._cleanup()

    async def _init_nova_session(self) -> None:
        """Phase 1 (on 'connected'): create stream + send sessionStart + promptStart."""
        self._nova_session = NovaSonicSession(
            on_audio_output=self._handle_nova_audio,
            on_transcript=self._on_transcript,
            on_session_end=self._handle_session_end,
        )
        await self._nova_session.start_session_and_prompt()
        logger.info("Nova Sonic session created, sessionStart + promptStart sent")

    async def _setup_nova_prompt(self) -> None:
        """Phase 2 (on 'start'): send systemPrompt + audioContentStart."""
        if not self._nova_session:
            return
        await self._nova_session.setup_system_prompt_and_audio()
        logger.info("Nova Sonic systemPrompt + audioContentStart sent")

    async def _send_hello_audio(self) -> None:
        """Send pre-recorded hello.pcm as a single instant write (no blocking)."""
        if not self._nova_session:
            return
        try:
            with open(self.HELLO_PCM_PATH, "rb") as f:
                hello_pcm = f.read()
            hello_b64 = base64.b64encode(hello_pcm).decode("ascii")
            await self._nova_session.send_audio(hello_b64)
            logger.info(f"Sent hello.pcm ({len(hello_pcm)} bytes) to Nova Sonic")
        except FileNotFoundError:
            logger.warning("hello.pcm not found, sending short silence instead")
            silence = struct.pack("<256h", *([0] * 256))
            await self._nova_session.send_audio(base64.b64encode(silence).decode("ascii"))

    async def _watchdog(self) -> None:
        """Restart the Nova Sonic session if no completionStart within 5 seconds."""
        await asyncio.sleep(5.0)
        if not self._active or not self._nova_session:
            return
        if self._nova_session.got_completion_start:
            return
        logger.warning("Watchdog: no completionStart after 5s, restarting session")
        old_session = self._nova_session
        self._nova_session = None
        await old_session.stop()
        # Each session creates its own client, so no shared state to corrupt
        self._nova_session = NovaSonicSession(
            on_audio_output=self._handle_nova_audio,
            on_transcript=self._on_transcript,
            on_session_end=self._handle_session_end,
        )
        await self._nova_session.start_session_and_prompt()
        await self._nova_session.setup_system_prompt_and_audio()
        await self._send_hello_audio()
        logger.info("Watchdog: retry session started")

    async def _handle_nova_audio(self, pcm_8k_bytes: bytes) -> None:
        """Convert Nova Sonic PCM 8kHz output to mulaw and send to Twilio."""
        if not self._active or not self._stream_sid:
            return
        mulaw_bytes = mulaw_encode(pcm_8k_bytes)
        mulaw_base64 = base64.b64encode(mulaw_bytes).decode("ascii")
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
