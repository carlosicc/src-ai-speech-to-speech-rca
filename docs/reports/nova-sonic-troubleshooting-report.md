# Nova Sonic Voice Integration — Troubleshooting Report

**Date:** 2026-05-18  
**Session context:** Debugging Twilio + Nova Sonic voice call in the RCA Agent Demo

---

## Summary

The voice pipeline (Twilio → ECS WebSocket → Nova Sonic → Twilio) has two resolved issues and one outstanding issue:

1. **RESOLVED** — Event loop starvation preventing Twilio WebSocket connection
2. **RESOLVED** — Nova Sonic session crashing due to unsupported `turnDetectionConfiguration`
3. **OUTSTANDING** — Nova Sonic intermittently fails to produce any output (audio or text) despite receiving and acknowledging audio input

---

## Issue 1: Twilio WebSocket Connection Timeout (RESOLVED)

**Root cause:** `diagnosis_agent.py` called the Strands agent synchronously (`response = agent(user_prompt)`) inside an async function scheduled on the main event loop. This blocked the event loop for ~28 seconds, preventing FastAPI from accepting Twilio's inbound WebSocket.

**Fix:** Changed to `response = await asyncio.to_thread(agent, user_prompt)` at line 368 of `src_backend/agents/diagnosis_agent.py`.

---

## Issue 2: Demo auto-resolving without DBA authorization (RESOLVED)

**Root cause:** The master agent's `update_incident_status` tool advanced the phase from CALLING → RECOVERING immediately after the LLM called it, without waiting for the voice session to complete.

**Fix:** Added a guard in `update_incident_status` that defers phase changes when `demo_state.phase == Phase.CALLING`.

---

## Issue 3: Nova Sonic not producing audio output (OUTSTANDING)

### Current State

Nova Sonic accepts the session, processes the system prompt and audio input, but intermittently produces **zero output** (no audio, no text response). The model acknowledges input via `usageEvent` deltas but never emits `completionStart`, `contentStart`, `audioOutput`, or `textOutput` events.

### What Works (observed once at 23:22 UTC)

One successful call produced:
- 1585 total events
- 1346 audio output chunks
- ASR transcriptions ("hello" detected correctly)
- Tool calls (`authenticate_user`, `check_service_health`)
- Full bidirectional conversation

### What Fails (all other attempts)

The session produces exactly 4 `usageEvent` events accounting for:
- 22 text tokens (system prompt overhead)
- 157 speech tokens (initial silence)
- 1 text token (separator)
- 43 text tokens (tool specs)

Then goes completely silent. No further events arrive despite continuous audio being sent from Twilio.

### Configuration (current deployed state)

**SDK:** `aws_sdk_bedrock_runtime==0.1.1`, `smithy-aws-core==0.1.1`  
**Model:** `amazon.nova-sonic-v1:0`  
**Region:** `us-east-1`  
**Voice:** `tiffany`  
**Audio format:** 8kHz, 16-bit PCM, mono (matching Twilio's native rate)

### Event Format Sent to Nova Sonic

```json
// 1. sessionStart
{"event": {"sessionStart": {"inferenceConfiguration": {"maxTokens": 1024, "topP": 0.9, "temperature": 0.7}}}}

// 2. promptStart
{"event": {"promptStart": {
  "promptName": "<uuid>",
  "textOutputConfiguration": {"mediaType": "text/plain"},
  "audioOutputConfiguration": {
    "audioType": "SPEECH", "encoding": "base64", "mediaType": "audio/lpcm",
    "sampleRateHertz": 8000, "sampleSizeBits": 16, "channelCount": 1, "voiceId": "tiffany"
  },
  "toolUseOutputConfiguration": {"mediaType": "application/json"},
  "toolConfiguration": {"tools": [...3 tools...]}
}}}

// 3. System prompt contentStart
{"event": {"contentStart": {
  "promptName": "<uuid>", "contentName": "<uuid>",
  "type": "TEXT", "interactive": true,
  "textInputConfiguration": {"mediaType": "text/plain"}
}}}

// 4. System prompt textInput
{"event": {"textInput": {
  "promptName": "<uuid>", "contentName": "<uuid>",
  "content": "You are an AI Operations Center voice agent...",
  "role": "SYSTEM"
}}}

// 5. System prompt contentEnd
{"event": {"contentEnd": {"promptName": "<uuid>", "contentName": "<uuid>"}}}

// 6. Audio contentStart
{"event": {"contentStart": {
  "promptName": "<uuid>", "contentName": "<uuid>",
  "type": "AUDIO", "interactive": true,
  "audioInputConfiguration": {
    "audioType": "SPEECH", "encoding": "base64", "mediaType": "audio/lpcm",
    "sampleRateHertz": 8000, "sampleSizeBits": 16, "channelCount": 1
  }
}}}

// 7. Audio chunks (continuous)
{"event": {"audioInput": {
  "promptName": "<uuid>", "contentName": "<uuid>",
  "content": "<base64 PCM 8kHz 16-bit>",
  "role": "USER"
}}}
```

### Initial Audio Strategy

After session setup, sends ~2 seconds of silence as 32ms chunks (256 samples each) with `asyncio.sleep(0.032)` between them. This blocks the Twilio media handler from forwarding real audio during those 2 seconds.

### What Was Tested

| Change | Result |
|--------|--------|
| Original code (24kHz, resampled) | 4 events, no output |
| Switch to 8kHz native (no resample) | Worked ONCE (1346 audio outputs), then 4 events on all subsequent attempts |
| `voiceId: "matthew"` | 4 events, no output |
| `voiceId: "tiffany"` | Worked once, then 4 events |
| Added `turnDetectionConfiguration` | Session crash: "current Sonic version does not support endpointing sensitivity config" |
| SDK upgrade 0.1.1 → 0.6.0 | 4 events, no output |
| SDK reverted to 0.1.1 | 4 events (same as current) |
| Single burst of 1s silence (no sleeps) | 4 events, no output |
| 2s chunked silence with 32ms sleeps | Worked once, then 4 events |
| Added `toolUseOutputConfiguration` | No difference to failure pattern |
| Removed extra `role` from `audioInput` | Caused regression (4 events); restored and it worked once |

### Key Observations

1. The successful run had `role: "USER"` in `audioInput` (current code has it)
2. The successful run used `interactive: true` on system prompt `contentStart` (current code has it)
3. The successful run used `role: "SYSTEM"` in `textInput` not `contentStart` (current code does this)
4. The pattern of 4 initial `usageEvent`s then silence is consistent across all failures
5. When it works, additional `usageEvent`s appear ~4 seconds after session start (accounting for incoming speech tokens from Twilio audio)
6. Twilio media chunks ARE received and forwarded to Nova Sonic in all cases

### Hypotheses for Next Session

1. **Timing/race condition in `_send_initial_audio`**: The 2-second blocking loop prevents Twilio media from being forwarded. When it "worked," perhaps the timing was lucky (Twilio media arrived just after the loop). Consider running initial silence as a background task.

2. **Nova Sonic needs real speech, not silence**: The official sample sends a pre-recorded `hello.pcm` file, not silence. Silence may not trigger turn-taking. Consider recording a short "hello" PCM file and sending that instead.

3. **Event ordering**: The official sample sets up the session from Twilio's `start` event handler (system prompt + audio start + hello audio all in sequence). Our code does the same but within an `await` chain that blocks Twilio processing.

4. **SDK compatibility**: SDK 0.1.1 is very old (latest is 0.6.0). The one successful run may have been a lucky session. Consider investigating if the SDK's event stream handling has known issues with 0.1.1.

5. **Model availability in us-east-1**: Check if there are regional issues or if the model is being throttled/rate-limited for this account.

### Files Modified in This Session

| File | Changes |
|------|---------|
| `src_backend/agents/diagnosis_agent.py:368` | `asyncio.to_thread` fix for event loop starvation |
| `src_backend/agents/master_agent.py:178-198` | `update_incident_status` guard during CALLING phase |
| `src_backend/voice/nova_sonic_client.py` | 8kHz audio config, event format fixes, debug logging, `toolUseOutputConfiguration` added |
| `src_backend/voice/twilio_handler.py` | Direct mulaw↔PCM conversion (no resampling), initial silence strategy |
| `src_backend/requirements.txt` | Tested SDK 0.6.0 (reverted to 0.1.1) |

### Reference Samples Available

- `/src_workspaces/references/sample-amazon-nova-sonic-twilio-integration/` — Official AWS Node.js sample (working Twilio+Nova Sonic integration)
- `/src_workspaces/references/sample-sonic-sip-server-js/` — SIP server sample
- `/src_workspaces/references/sample-nova-sonic-websocket-agentcore/` — WebSocket with AgentCore

### Recommended Next Steps

1. **Use a real `hello.pcm` file** instead of silence — extract from the official sample or record one
2. **Run initial audio as background task** so Twilio media isn't blocked
3. **Add a retry mechanism** — if no `completionStart` event within 5 seconds, restart the Nova Sonic session
4. **Test locally** outside of the demo flow — create a standalone script that connects to Nova Sonic from the ECS container directly to isolate whether the issue is in our code or in the service
5. **Check CloudTrail/Service Health** for Nova Sonic in us-east-1 for throttling or degraded availability
