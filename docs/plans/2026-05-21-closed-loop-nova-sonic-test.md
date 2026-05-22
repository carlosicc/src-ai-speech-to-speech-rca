# Plan: Closed-Loop Nova Sonic Test Harness (No Twilio, No Human)

**Status**: COMPLETED (2026-05-21)  
**Result**: Test harness built and passing. Voice quality issues fixed. Demo working well.

**Goal**: Build a test harness that validates the Nova Sonic voice flow end-to-end using pre-recorded WAV files instead of real phone calls. Runs in CI or locally with just AWS credentials.

**Why**: Real Twilio calls are expensive, slow, and non-deterministic. This harness feeds known-good audio directly to Nova Sonic's bidirectional API and asserts on tool invocations — the same technique used in production debugging.

---

## Outcome Summary

### What Was Built
- **Test harness** (`tests/harness/`) — streams WAV audio to Nova Sonic, asserts tool invocations
- **Audio fixtures** (`tests/fixtures/audio/`) — Polly-generated WAV at 16kHz
- **4 integration tests** — all passing (~80s total):
  - `test_correct_passphrase_invokes_authenticate` — "REDACTED_PASSPHRASE" → auth success
  - `test_wrong_passphrase_fails_auth` — "bravo midnight" → auth failed
  - `test_full_flow_auth_then_restore` — "yes restore" → restore_connectivity called
  - `test_silence_no_tools` — silence → no tools invoked

### Voice Quality Fixes (Production)
Two changes that transformed voice UX from "terrible overlapping" to "great natural conversation":

1. **`turnDetectionConfiguration: { endpointingSensitivity: "MEDIUM" }`** — Real Nova 2 Sonic API parameter ([docs](https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-input-events.html)). Without it, default turn detection waits ~10s. With MEDIUM, ~1-2s.

2. **Barge-in handling** — On `stopReason: "INTERRUPTED"` (real Nova Sonic event), send Twilio `clear` event to flush audio playback buffer. Without this, Twilio keeps playing buffered audio causing voice overlap.

### Config Changes (Deployed)
- `NOVA_SONIC_REGION`: `us-east-1` → `eu-north-1` (lower latency from Europe)
- `VOICE_PASSPHRASE`: `REDACTED_PASSPHRASE` → `REDACTED_PASSPHRASE`

### Run Commands
```bash
# Generate audio fixtures (one-time)
.venv/bin/python scripts/generate_test_audio.py

# Run closed-loop tests
.venv/bin/pytest tests/integration/test_nova_sonic_closed_loop.py -v
```

---

## Context

- **Production flow**: Twilio → mulaw decode → PCM 8kHz → Nova Sonic → tools → phase advance
- **Test flow**: WAV file → resample to required format → Nova Sonic → tools → assert outcome
- **Current code**: `src_backend/voice/nova_sonic_client.py` already implements the full bidirectional stream protocol
- **Model**: `amazon.nova-2-sonic-v1:0` in `eu-north-1`

---

## Critical Nova Sonic 2.0 Facts (From Production Experience)

These are non-obvious details that will cause silent failures if not respected:

### Audio Formats — Input ≠ Output
- **Input to model**: 16kHz, 16-bit, mono PCM (confirmed from reference samples)
- **Output from model**: configurable — our production uses 8kHz for Twilio compatibility
- Our current code sends 8kHz input (Twilio's native rate). For the test harness, we should use 16kHz (Nova Sonic's native input rate) for best quality.

### Model ID
- `amazon.nova-2-sonic-v1:0` (this is what's deployed and working)
- Available in: `us-east-1`, `us-west-2`, `eu-north-1`, `ap-northeast-1`
- **Deployed in**: `eu-north-1` (Stockholm — low latency for EU demo)

### Session Lifecycle — Mandatory Event Sequence
1. `sessionStart` (inferenceConfiguration + optional turnDetectionConfiguration)
2. `promptStart` (audio output config, tool definitions)
3. `contentStart` (TEXT) → `textInput` (system prompt) → `contentEnd`
4. `contentStart` (AUDIO, input config)
5. Stream `audioInput` events (PCM chunks as base64)
6. `contentEnd` (audio) → `promptEnd` → `sessionEnd`
7. Concurrently: receive and handle response events

### Turn Detection (`endpointingSensitivity`) — CRITICAL FOR GOOD UX
```json
{
  "turnDetectionConfiguration": {
    "endpointingSensitivity": "MEDIUM"
  }
}
```
- `LOW` = ~2 second pause before model responds (good for deliberate passphrase)
- `MEDIUM` = natural conversation (~1-2s) — **RECOMMENDED DEFAULT** per AWS docs
- `HIGH` = fast responses, may cut off mid-sentence (used in test harness)
- **Without this field, default turn detection is extremely conservative (~10s)** — this was the primary cause of latency

### Barge-In Handling — CRITICAL FOR TWILIO
When Nova Sonic sends `contentEnd` with `stopReason: "INTERRUPTED"`:
- The model has detected user speech and stopped generating
- Client MUST clear its audio playback buffer immediately
- For Twilio: send `{"event": "clear", "streamSid": "..."}` to flush buffered audio
- Without this, Twilio keeps playing old audio → voice overlap

### Barge-In JSON Pollution
Nova Sonic sends `{ "interrupted": true }` as literal text in transcript events during barge-in. Filter this server-side.

### Connection Limit
8 minutes per bidirectional stream. Not relevant for testing but good to know.

### System Prompt Gotcha
Without explicit instructions to NOT repeat the greeting, the model repeats its opening message every turn. For testing, use a minimal prompt that just listens and invokes tools.

---

## What We're Testing

| Test Case | Input Audio | Expected Outcome |
|-----------|-------------|-----------------|
| Happy path | WAV of "REDACTED_PASSPHRASE" | `authenticate_user` tool called with matching passphrase |
| Wrong passphrase | WAV of "REDACTED_PASSPHRASE" | `authenticate_user` tool called but returns `failed` |
| Full flow | WAV of "REDACTED_PASSPHRASE" + "yes fix it" | `authenticate_user` → success, then `restore_connectivity` called |
| No speech | 5s of silence | No tool invoked, session ends cleanly |

---

## Implementation Plan

### Step 1 — Audio Fixtures

Create WAV files at 16kHz 16-bit mono using Amazon Polly (deterministic, reproducible):

```python
# scripts/generate_test_audio.py
import boto3
import wave

polly = boto3.client("polly", region_name="us-east-1")

phrases = {
    "correct_passphrase": "REDACTED_PASSPHRASE",
    "wrong_passphrase": "REDACTED_PASSPHRASE",
    "authorize_fix": "yes, restore the firewall",
}

for name, text in phrases.items():
    response = polly.synthesize_speech(
        Text=text,
        OutputFormat="pcm",
        SampleRate="16000",
        VoiceId="Joanna",
    )
    pcm_bytes = response["AudioStream"].read()
    
    with wave.open(f"tests/fixtures/audio/{name}.wav", "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm_bytes)
```

Store in `tests/fixtures/audio/`. Gitignore them if large, or commit since they're small (~50KB each).

### Step 2 — Nova Sonic Test Client

Create `tests/harness/nova_sonic_test_client.py` — a simplified version of our production `nova_sonic_client.py`, adapted for testing:

**Key differences from production client:**
- Accepts audio from a file (iterator of PCM chunks) instead of live WebSocket
- Uses 16kHz input (native) instead of 8kHz (Twilio)
- Collects tool invocations in a list for assertion
- Runs to completion (sends all audio, waits for tools, then closes)
- No watchdog needed — deterministic input
- Adds `turnDetectionConfiguration: { endpointingSensitivity: "LOW" }` to `sessionStart`

**Core function:**
```python
@dataclass
class TestSessionResult:
    tool_invocations: list[dict]  # [{name, input, result}, ...]
    transcript: list[str]         # user + assistant text
    audio_output_count: int
    error: str | None

async def run_nova_sonic_test(
    audio_path: str,
    system_prompt: str,
    tools: list[dict],
    tool_handler: Callable,
    region: str = "us-east-1",
    chunk_size: int = 3200,  # 100ms at 16kHz 16-bit
) -> TestSessionResult:
    ...
```

**Event sequence:**
1. Open bidirectional stream
2. Send `sessionStart` with `turnDetectionConfiguration: { endpointingSensitivity: "LOW" }`
3. Send `promptStart` with tools and audio output config (16kHz for testing)
4. Send system prompt (contentStart/textInput/contentEnd)
5. Send audioContentStart (16kHz, 16-bit, mono)
6. Stream audio chunks from file with small delays between chunks (simulate real-time: `await asyncio.sleep(chunk_duration)`)
7. After all audio sent, send contentEnd + wait for model to respond + invoke tools
8. Collect tool invocations and return

### Step 3 — Tool Handler for Tests

Reuse our existing `voice/voice_tools.py` functions but wrap them for testability:

```python
# tests/harness/tool_handler.py
from voice.voice_tools import _authenticate_user, _check_service_health

async def test_tool_handler(tool_name: str, tool_input: dict) -> dict:
    """Execute tools and return results, same as production but without phase advancement."""
    if tool_name == "authenticate_user":
        return _authenticate_user(tool_input.get("passphrase", ""))
    elif tool_name == "check_service_health":
        return _check_service_health(tool_input.get("service", "aurora-db"))
    elif tool_name == "restore_connectivity":
        # Don't actually call AWS in tests — just return success
        return {"status": "success", "message": "Mock: firewall rule restored"}
    return {"status": "error", "error": f"Unknown tool: {tool_name}"}
```

### Step 4 — Test Cases

```python
# tests/integration/test_nova_sonic_closed_loop.py

@pytest.mark.asyncio
async def test_correct_passphrase_invokes_authenticate():
    """Nova Sonic hears 'REDACTED_PASSPHRASE' and calls authenticate_user tool."""
    result = await run_nova_sonic_test(
        audio_path="tests/fixtures/audio/correct_passphrase.wav",
        system_prompt=VOICE_AGENT_SYSTEM_PROMPT,
        tools=TOOL_SPECS,
        tool_handler=test_tool_handler,
    )
    assert result.error is None
    assert any(t["name"] == "authenticate_user" for t in result.tool_invocations)
    auth_call = next(t for t in result.tool_invocations if t["name"] == "authenticate_user")
    assert "aurora" in auth_call["input"]["passphrase"].lower()

@pytest.mark.asyncio
async def test_wrong_passphrase_fails_auth():
    """Nova Sonic hears 'REDACTED_PASSPHRASE' — tool called but auth fails."""
    result = await run_nova_sonic_test(
        audio_path="tests/fixtures/audio/wrong_passphrase.wav",
        system_prompt=VOICE_AGENT_SYSTEM_PROMPT,
        tools=TOOL_SPECS,
        tool_handler=test_tool_handler,
    )
    auth_call = next(t for t in result.tool_invocations if t["name"] == "authenticate_user")
    assert auth_call["result"]["status"] == "failed"
```

### Step 5 — Integrate `endpointingSensitivity` into Production

While building the test harness, also add `turnDetectionConfiguration` to the production `nova_sonic_client.py`. This may reduce the ~10s latency issue:

```python
# In _send_session_start():
await self._send_event({
    "event": {
        "sessionStart": {
            "inferenceConfiguration": {
                "maxTokens": 1024,
                "topP": 0.9,
                "temperature": 0.7,
            },
            "turnDetectionConfiguration": {
                "endpointingSensitivity": "MEDIUM",
            },
        }
    }
})
```

Use `MEDIUM` for production (natural conversation), `LOW` for the test harness (deliberate single utterance).

---

## File Structure

```
tests/
├── fixtures/
│   └── audio/
│       ├── correct_passphrase.wav
│       ├── wrong_passphrase.wav
│       └── authorize_fix.wav
├── harness/
│   ├── __init__.py
│   ├── nova_sonic_test_client.py
│   └── tool_handler.py
└── integration/
    ├── __init__.py
    ├── test_demo_loop.py          (existing)
    └── test_nova_sonic_closed_loop.py  (new)

scripts/
└── generate_test_audio.py
```

---

## Dependencies (additions to requirements.txt or test requirements)

```
# Only needed for generating audio fixtures
boto3  # already have — for Polly
# Only needed if loading non-16kHz WAV files
scipy>=1.11  # for resampling
```

No new runtime dependencies. `wave` module is stdlib.

---

## Run Configuration

```bash
# Generate audio fixtures (one-time)
.venv/bin/python scripts/generate_test_audio.py

# Run closed-loop tests
.venv/bin/pytest tests/integration/test_nova_sonic_closed_loop.py -v
```

Requires: AWS credentials with `bedrock:InvokeModelWithBidirectionalStream` permission on `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-sonic-v1:0`.

---

## ~~Bonus: Latency Investigation~~ ✓ RESOLVED

**Root cause confirmed**: Turn detection (waiting for silence). Without `turnDetectionConfiguration`, Nova Sonic used very conservative defaults (~10s silence before responding).

**Fix**: `endpointingSensitivity: "MEDIUM"` reduced response time to ~1-2s. Used `HIGH` in test harness for even faster detection on short utterances.

**Additional fix**: Barge-in overlap was caused by Twilio continuing to play buffered audio after Nova Sonic detected interruption. Fixed by sending Twilio `clear` event on `stopReason: "INTERRUPTED"`.

**Note on echo**: Twilio's `<Stream>` defaults to `track="inbound_track"` (user voice only, not mixed). Phone echo from earpiece→mic is minimal but can be eliminated by user muting or using earbuds.

---

## Known Issues to Fix in This Session

### 1. Call not answered → Nova Sonic keeps running in background

**Symptom**: If the phone call goes to voicemail (or is not answered), Nova Sonic continues running and the transcript appears in the UI as if the agent is talking to someone. The session should end if the call is not answered.

**Likely cause**: Twilio connects the Media Stream even when voicemail answers (voicemail is technically "answered" from Twilio's perspective). Nova Sonic hears the voicemail greeting silence/beep and starts talking.

**Fix options**:
- Add a Twilio `machineDetection` parameter to the outbound call (`machine_detection="Enable"` or `"DetectMessageEnd"`). If Twilio detects an answering machine, hang up immediately.
- Or: add a timeout in the TwilioMediaStreamHandler — if no real user speech detected within N seconds of audio, abort the session.

### 2. Too long from "Break DB" to phone ringing (~45-60 seconds)

**Symptom**: From pressing "Break DB" to the phone actually ringing takes over a minute. Breakdown from UI logs:

```
20:59:14 - Break DB pressed
20:59:16 - Diagnosis starts
20:59:44 - RCA complete (28 seconds for diagnosis!)
20:59:49 - activate_voice_call tool called
20:59:52 - update_incident_status
20:59:58 - Twilio call placed (44 seconds from button press to call)
21:00:24 - Nova Sonic first speaks (70 seconds total!)
```

**Bottlenecks**:
1. **Diagnosis agent: 28 seconds** (20:59:16 → 20:59:44). The Strands/Claude diagnosis agent runs 4 tools + generates a full RCA report. This is the biggest delay.
2. **Master agent overhead: ~5s** between diagnosis complete and voice call placement
3. **Twilio call setup + ring time: ~10s** (20:59:58 → answering)
4. **Nova Sonic first response: ~26s** (21:00:24 - 20:59:58) — includes ring time + session setup + model generating first utterance

**Fix options for the diagnosis delay**:
- Use a faster model for diagnosis (Claude Haiku instead of Sonnet)
- Skip the full RCA text generation — just run the tools and pass raw results
- Run diagnosis and voice call in parallel (start the call while diagnosis is still running, brief the voice agent with results when ready)
- Pre-compute a simulated RCA (since we already know the root cause — it's a demo)
- Reduce `PHASE_DURATIONS[Phase.INCIDENT_DETECTED]` from 2s to 1s

**Note**: For a 3-minute demo loop, spending 70 seconds just to get to "hello" is too long. Target should be under 30 seconds from button press to the agent speaking.

---

## ~~MUST DO: Change Nova Sonic Region to eu-north-1~~ ✓ DONE

Changed in all locations:
- `src_backend/shared/config.py` — default changed to `eu-north-1`
- `src_infra/stack_backend.py` — container env var updated
- Test harness — uses `eu-north-1`
- Deployed and confirmed working.

---

## Notes for Implementation Session

1. The production client (`nova_sonic_client.py`) uses the `aws_sdk_bedrock_runtime` Smithy SDK (0.6.0). The test harness should use the same SDK — not raw boto3 — since that's what we deploy with.

2. Audio chunk streaming should simulate real-time pace (`asyncio.sleep(chunk_duration_seconds)` between chunks). Sending all audio instantly may confuse the turn detector.

3. The `hello.pcm` file we already have in `src_backend/voice/assets/` is 8kHz. For the test harness using 16kHz input, generate new fixtures via Polly at 16kHz.

4. Our production audio path is 8kHz because Twilio sends mulaw 8kHz. If we change the test harness to 16kHz, the test validates Nova Sonic's tool-calling behavior but NOT the exact audio encoding path of production. That's fine — the purpose is to test the agent logic, not the Twilio bridge.

5. Model ID discrepancy: The Cowork reference says `amazon.nova-sonic-v2:0` but our working deployment uses `amazon.nova-2-sonic-v1:0`. Use what's deployed and working.
