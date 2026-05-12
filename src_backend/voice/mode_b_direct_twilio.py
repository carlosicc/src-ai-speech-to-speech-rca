"""Mode B: Direct Bedrock + Twilio voice session.

Places an outbound call via Twilio REST API, then handles the Twilio Media Stream
WebSocket connection back from Twilio, bridging audio to/from Nova Sonic.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine

from shared.state import demo_state
from voice.twilio_handler import TwilioMediaStreamHandler, place_outbound_call

logger = logging.getLogger(__name__)


class TwilioVoiceSession:
    """Mode B voice session: Twilio phone call bridged to Direct Bedrock Nova Sonic.

    Lifecycle:
    1. start() places outbound call via Twilio REST API
    2. Twilio connects a Media Stream WebSocket to /twilio/media-stream
    3. TwilioMediaStreamHandler bridges audio between Twilio and Nova Sonic
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
        self._handler: TwilioMediaStreamHandler | None = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def call_sid(self) -> str | None:
        return self._call_sid

    async def start(self) -> None:
        """Place the outbound call. Twilio will connect back via Media Stream WebSocket."""
        self._active = True
        phone_number = demo_state.phone_number

        logger.info(f"Mode B: placing outbound call to {phone_number}")
        self._call_sid = await place_outbound_call(phone_number, self._media_stream_url)

        if not self._call_sid:
            logger.error("Mode B: failed to place outbound call")
            self._active = False
            await self._on_session_end()

    def set_handler(self, handler: TwilioMediaStreamHandler) -> None:
        """Attach the Twilio Media Stream handler once Twilio connects back."""
        self._handler = handler

    async def stop(self) -> None:
        """Stop the voice session and hang up the call."""
        if not self._active:
            return
        self._active = False
        if self._handler and self._handler.active:
            await self._handler.send_clear()
        logger.info("Mode B: session stopped")
