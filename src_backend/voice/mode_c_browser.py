import asyncio
import base64
import logging
import struct
from typing import Any, Callable, Coroutine

from voice.nova_sonic_client import NovaSonicSession

logger = logging.getLogger(__name__)

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000


def resample_16k_to_24k(pcm_16k: bytes) -> bytes:
    """Resample PCM 16-bit mono from 16kHz to 24kHz using linear interpolation."""
    samples_in = struct.unpack(f"<{len(pcm_16k) // 2}h", pcm_16k)
    num_in = len(samples_in)
    if num_in < 2:
        return pcm_16k

    ratio = INPUT_SAMPLE_RATE / OUTPUT_SAMPLE_RATE
    num_out = int(num_in / ratio)
    samples_out = []

    for i in range(num_out):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = src_pos - idx

        if idx + 1 < num_in:
            sample = int(samples_in[idx] * (1 - frac) + samples_in[idx + 1] * frac)
        else:
            sample = samples_in[idx]

        sample = max(-32768, min(32767, sample))
        samples_out.append(sample)

    return struct.pack(f"<{len(samples_out)}h", *samples_out)


class BrowserVoiceSession:
    def __init__(
        self,
        on_audio_output: Callable[[str], Coroutine[Any, Any, None]],
        on_transcript: Callable[[str, str], Coroutine[Any, Any, None]],
        on_session_end: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        self._on_audio_output = on_audio_output
        self._on_transcript = on_transcript
        self._on_session_end = on_session_end
        self._session: NovaSonicSession | None = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    async def start(self) -> None:
        logger.info("Starting browser voice session (Mode C)")
        self._active = True
        self._session = NovaSonicSession(
            on_audio_output=self._handle_audio_output,
            on_transcript=self._on_transcript,
            on_session_end=self._handle_session_end,
        )
        await self._session.start()

    async def receive_audio(self, pcm_16k_base64: str) -> None:
        if not self._active or not self._session:
            return
        pcm_16k = base64.b64decode(pcm_16k_base64)
        pcm_24k = resample_16k_to_24k(pcm_16k)
        pcm_24k_base64 = base64.b64encode(pcm_24k).decode("ascii")
        await self._session.send_audio(pcm_24k_base64)

    async def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._session:
            await self._session.stop()
            self._session = None
        logger.info("Browser voice session stopped")

    async def _handle_audio_output(self, pcm_24k: bytes) -> None:
        pcm_24k_base64 = base64.b64encode(pcm_24k).decode("ascii")
        await self._on_audio_output(pcm_24k_base64)

    async def _handle_session_end(self) -> None:
        self._active = False
        self._session = None
        await self._on_session_end()
