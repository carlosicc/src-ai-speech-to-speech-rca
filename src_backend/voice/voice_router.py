import logging
from typing import Any, Callable, Coroutine

from shared.state import demo_state
from voice.mode_b_direct_twilio import TwilioVoiceSession
from voice.mode_c_browser import BrowserVoiceSession

logger = logging.getLogger(__name__)


class VoiceRouter:
    def __init__(self) -> None:
        self._browser_session: BrowserVoiceSession | None = None
        self._twilio_session: TwilioVoiceSession | None = None
        self._media_stream_url: str = ""

    @property
    def active(self) -> bool:
        if self._browser_session:
            return self._browser_session.active
        if self._twilio_session:
            return self._twilio_session.active
        return False

    def set_media_stream_url(self, url: str) -> None:
        """Set the public WebSocket URL that Twilio will connect to for Media Streams."""
        self._media_stream_url = url

    async def start_session(
        self,
        on_audio_output: Callable[[str], Coroutine[Any, Any, None]],
        on_transcript: Callable[[str, str], Coroutine[Any, Any, None]],
        on_session_end: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        mode = demo_state.voice_mode

        if mode == "mode_b":
            if not self._media_stream_url:
                logger.warning("Mode B: no media_stream_url configured, falling back to Mode C")
                await self._start_browser_session(on_audio_output, on_transcript, on_session_end)
                return
            logger.info("Voice router: starting Mode B (Twilio + direct Bedrock)")
            self._twilio_session = TwilioVoiceSession(
                on_transcript=on_transcript,
                on_session_end=on_session_end,
                media_stream_url=self._media_stream_url,
            )
            await self._twilio_session.start()

        elif mode == "mode_c":
            logger.info("Voice router: starting Mode C (browser + direct Bedrock)")
            await self._start_browser_session(on_audio_output, on_transcript, on_session_end)

        elif mode == "mode_a":
            logger.warning("Mode A (AgentCore) not yet implemented, falling back to Mode C")
            await self._start_browser_session(on_audio_output, on_transcript, on_session_end)

        else:
            logger.error(f"Unknown voice mode: {mode}")

    async def _start_browser_session(
        self,
        on_audio_output: Callable[[str], Coroutine[Any, Any, None]],
        on_transcript: Callable[[str, str], Coroutine[Any, Any, None]],
        on_session_end: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        self._browser_session = BrowserVoiceSession(
            on_audio_output=on_audio_output,
            on_transcript=on_transcript,
            on_session_end=on_session_end,
        )
        await self._browser_session.start()

    async def receive_audio(self, pcm_16k_base64: str) -> None:
        if self._browser_session and self._browser_session.active:
            await self._browser_session.receive_audio(pcm_16k_base64)

    async def stop_session(self) -> None:
        if self._browser_session:
            await self._browser_session.stop()
            self._browser_session = None
        if self._twilio_session:
            await self._twilio_session.stop()
            self._twilio_session = None
        logger.info("Voice router: session stopped")

    @property
    def twilio_session(self) -> TwilioVoiceSession | None:
        return self._twilio_session


voice_router = VoiceRouter()
