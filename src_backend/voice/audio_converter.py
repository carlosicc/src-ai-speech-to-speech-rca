"""Audio format conversion: mulaw 8kHz ↔ PCM 16-bit 24kHz.

Twilio Media Streams send/receive G.711 μ-law (8-bit, 8kHz mono).
Nova Sonic expects/produces PCM (16-bit signed, 24kHz mono).
"""

import struct

MULAW_BIAS = 0x84
MULAW_MAX = 0x7FFF
MULAW_CLIP = 32635

# Precomputed lookup table for mulaw decode (256 entries)
_MULAW_DECODE_TABLE: list[int] = []

def _build_decode_table() -> list[int]:
    table = []
    for i in range(256):
        complement = ~i & 0xFF
        sign = complement & 0x80
        exponent = (complement >> 4) & 0x07
        mantissa = complement & 0x0F
        sample = (mantissa << 4) + MULAW_BIAS
        sample <<= exponent
        sample -= MULAW_BIAS
        if sign:
            sample = -sample
        sample = max(-32768, min(32767, sample))
        table.append(sample)
    return table

_MULAW_DECODE_TABLE = _build_decode_table()


def mulaw_decode(mulaw_bytes: bytes) -> bytes:
    """Decode G.711 μ-law (8-bit) to PCM 16-bit signed little-endian."""
    samples = [_MULAW_DECODE_TABLE[b] for b in mulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)


def _encode_mulaw_sample(sample: int) -> int:
    """Encode a single 16-bit PCM sample to 8-bit μ-law."""
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    if sample > MULAW_CLIP:
        sample = MULAW_CLIP
    sample += MULAW_BIAS

    exponent = 7
    for exp in range(7, -1, -1):
        if sample & (1 << (exp + 7)):
            exponent = exp
            break

    mantissa = (sample >> (exponent + 3)) & 0x0F
    mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
    return mulaw_byte


def mulaw_encode(pcm_bytes: bytes) -> bytes:
    """Encode PCM 16-bit signed little-endian to G.711 μ-law (8-bit)."""
    num_samples = len(pcm_bytes) // 2
    samples = struct.unpack(f"<{num_samples}h", pcm_bytes)
    return bytes(_encode_mulaw_sample(s) for s in samples)


def resample_8k_to_24k(pcm_8k: bytes) -> bytes:
    """Upsample PCM 16-bit from 8kHz to 24kHz using linear interpolation (3x)."""
    num_samples = len(pcm_8k) // 2
    if num_samples < 2:
        return pcm_8k
    samples_in = struct.unpack(f"<{num_samples}h", pcm_8k)
    samples_out: list[int] = []

    for i in range(num_samples - 1):
        s0 = samples_in[i]
        s1 = samples_in[i + 1]
        samples_out.append(s0)
        samples_out.append(s0 + (s1 - s0) // 3)
        samples_out.append(s0 + 2 * (s1 - s0) // 3)

    samples_out.append(samples_in[-1])
    samples_out.append(samples_in[-1])
    samples_out.append(samples_in[-1])

    return struct.pack(f"<{len(samples_out)}h", *samples_out)


def resample_24k_to_8k(pcm_24k: bytes) -> bytes:
    """Downsample PCM 16-bit from 24kHz to 8kHz (pick every 3rd sample)."""
    num_samples = len(pcm_24k) // 2
    if num_samples < 3:
        return pcm_24k
    samples_in = struct.unpack(f"<{num_samples}h", pcm_24k)
    samples_out = [samples_in[i] for i in range(0, num_samples, 3)]
    return struct.pack(f"<{len(samples_out)}h", *samples_out)


def resample_8k_to_16k(pcm_8k: bytes) -> bytes:
    """Upsample PCM 16-bit from 8kHz to 16kHz using linear interpolation (2x)."""
    num_samples = len(pcm_8k) // 2
    if num_samples < 2:
        return pcm_8k
    samples_in = struct.unpack(f"<{num_samples}h", pcm_8k)
    samples_out: list[int] = []

    for i in range(num_samples - 1):
        s0 = samples_in[i]
        s1 = samples_in[i + 1]
        samples_out.append(s0)
        samples_out.append((s0 + s1) // 2)

    samples_out.append(samples_in[-1])
    samples_out.append(samples_in[-1])

    return struct.pack(f"<{len(samples_out)}h", *samples_out)


def resample_16k_to_8k(pcm_16k: bytes) -> bytes:
    """Downsample PCM 16-bit from 16kHz to 8kHz (pick every 2nd sample)."""
    num_samples = len(pcm_16k) // 2
    if num_samples < 2:
        return pcm_16k
    samples_in = struct.unpack(f"<{num_samples}h", pcm_16k)
    samples_out = [samples_in[i] for i in range(0, num_samples, 2)]
    return struct.pack(f"<{len(samples_out)}h", *samples_out)


def twilio_to_nova(mulaw_8k_base64_payload: bytes) -> str:
    """Full pipeline: mulaw 8kHz bytes → PCM 24kHz base64 string for Nova Sonic."""
    import base64
    pcm_8k = mulaw_decode(mulaw_8k_base64_payload)
    pcm_24k = resample_8k_to_24k(pcm_8k)
    return base64.b64encode(pcm_24k).decode("ascii")


def nova_to_twilio(pcm_24k_bytes: bytes) -> str:
    """Full pipeline: PCM 24kHz bytes → mulaw 8kHz base64 string for Twilio."""
    import base64
    pcm_8k = resample_24k_to_8k(pcm_24k_bytes)
    mulaw_bytes = mulaw_encode(pcm_8k)
    return base64.b64encode(mulaw_bytes).decode("ascii")
