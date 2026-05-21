# Report: Nova Sonic Voice Session — Status & Issues

**Date**: 2026-05-20/21  
**Author**: Claude Code session  
**Purpose**: Full context handoff for next session to debug remaining voice call issues

---

## Current State (Deployed)

### Infrastructure
- **ECS**: 1/1 running, rollout COMPLETED
- **Model**: `amazon.nova-2-sonic-v1:0` (Nova Sonic 2.0) — just deployed, **not yet tested**
- **SDK versions** (in Docker container):
  - `aws_sdk_bedrock_runtime>=0.6.0` (latest)
  - `smithy-aws-core>=0.6.0` (latest)
  - `smithy-aws-event-stream>=0.3.0` (latest)
  - `smithy-http>=0.4.0` (latest)
  - `strands-agents>=1.40.0` (latest)
- **Region**: us-east-1 (Nova Sonic)
- **Voice timeout**: 90 seconds

### Key Files
| File | Purpose |
|------|---------|
| `src_backend/voice/nova_sonic_client.py` | Nova Sonic bidirectional streaming session |
| `src_backend/voice/twilio_handler.py` | Twilio Media Stream ↔ Nova Sonic bridge |
| `src_backend/voice/voice_tools.py` | Tools: authenticate_user, restore_connectivity, check_service_health |
| `src_backend/voice/mode_b_direct_twilio.py` | Mode B: outbound Twilio call placement |
| `src_backend/demo_controller.py` | Phase orchestration (DIAGNOSING → CALLING → RECOVERING) |
| `src_backend/shared/config.py` | Config: NOVA_SONIC_MODEL_ID, TWILIO_CALLING_TIMEOUT, VOICE_PASSPHRASE |
| `cdk.json` | CDK context with model IDs (authoritative source for ECS env vars) |

---

## Demo Flow (How It Works)

```
1. User clicks "Break DB" → revokes SG rule (instant) → triggers incident
2. Master agent (Strands/Claude) runs diagnosis → identifies missing SG rule
3. Master agent calls activate_voice_call tool → sets phase to CALLING
4. _run_phases() loop enters _run_voice_session() → places Twilio outbound call
5. Twilio connects → Media Stream WebSocket opens to our /twilio/media-stream endpoint
6. TwilioMediaStreamHandler creates NovaSonicSession:
   - Phase 1 (on "connected"): open bidi stream → send sessionStart + promptStart
   - Phase 2 (on "start"): send systemPrompt + audioContentStart + hello.pcm
7. Nova Sonic speaks to user, asks for passphrase
8. User says "REDACTED_PASSPHRASE" → authenticate_user tool → success
9. Nova Sonic asks for authorization → user says "yes"
10. restore_connectivity tool → restores SG rule → phase → RECOVERING
11. Phase advances: RECOVERING → RESOLVED → HEALTHY
```

---

## Bugs Fixed in This Session

### 1. "First event must be a SessionStart" (FIXED)
**Root cause**: Response task was started before `sessionStart` was sent.  
**Fix**: Send `sessionStart` + `promptStart` immediately after opening the stream, BEFORE `asyncio.create_task(self._process_responses())`.

### 2. "Role is required when no content state role exists" (FIXED)
**Root cause**: Tool result `contentStart` event was missing `"role": "TOOL"` and had `"interactive": False`.  
**Fix**: Added `"role": "TOOL"`, `"interactive": True`, and `"status"` field to tool result events in `_send_tool_result()`.

### 3. Demo auto-resolving while still on the phone (FIXED)
**Root cause**: Two `_run_phases()` tasks racing — one from `trigger_incident()`, another from the WebSocket handler.  
**Fix**: Removed duplicate `asyncio.create_task(demo_controller._run_phases())` from `main.py` WebSocket handler. Added `continue` guard in `_run_phases()` after master orchestration when phase is CALLING.

### 4. Watchdog retry crashing with "No open content found" (FIXED)
**Root cause**: Twilio media chunks were being forwarded to the new session before it finished setup (media handler saw `self._nova_session` was already set).  
**Fix**: Set `self._nova_session = None` during setup, only assign the new session after full initialization.

### 5. Nova Sonic errors auto-advancing phases (FIXED)
**Root cause**: `_process_responses()` was calling `self._on_session_end()` in the `finally` block even on errors, which advanced the phase.  
**Fix**: Only call `_on_session_end()` when `error_occurred is False`.

### 6. Voice timeout too short (FIXED)
**Root cause**: `TWILIO_CALLING_TIMEOUT` was 45s but the full conversation takes 50-60s.  
**Fix**: Increased to 90s.

### 7. Nova Sonic model still v1 despite config change (FIXED — just deployed)
**Root cause**: `cdk.json` context had `amazon.nova-sonic-v1:0` which overrides the default in `stack_backend.py` and `shared/config.py`.  
**Fix**: Updated `cdk.json` to `amazon.nova-2-sonic-v1:0`. Confirmed ECS task definition now has v2.

---

## Remaining Issues

### Issue A: Nova Sonic v1 Intermittently Not Responding — RESOLVED by v2 Upgrade
**Symptom**: Session starts correctly but no `completionStart` or audio output generated. Model stalls.  
**Resolution**: Upgraded to `amazon.nova-2-sonic-v1:0`. First test with v2 produced `completionStart` in < 1 second. No watchdog needed. Issue was v1-specific.

### Issue B: Call Dropped After Passphrase Prompt — RESOLVED (was v1)
**Resolution**: Was only observed on v1. The v2 test completed the full 2-minute conversation successfully.

### Issue C: Unclosed aiohttp Client Sessions (Cosmetic — Low Priority)
**Symptom**: `[ERROR] asyncio: Unclosed client session` appears after session cleanup.  
**Impact**: None functional — just log noise.  
**Cause**: The Smithy HTTP client used by `aws_sdk_bedrock_runtime` isn't being explicitly closed.

### Issue D: ~10s Latency on User Speech (UX — Future Fix)
**Symptom**: User speaks but Nova Sonic takes ~10 seconds to process and respond. Feels like the agent is ignoring you.  
**Observed in**: Successful v2 test (2026-05-21 03:00 UTC). User said passphrase, ~10s elapsed before `authenticate_user` tool was called.  
**Possible causes**:
- Nova Sonic v2 end-of-turn detection (waits for silence to confirm user finished speaking)
- Audio buffering in the Twilio → ECS → Bedrock pipeline
- Model processing latency for tool invocation decisions
**Priority**: Future improvement — demo works end-to-end, just feels sluggish.

---

## Latest Logs (2026-05-21 03:00–03:03 UTC) — SUCCESSFUL END-TO-END

**Model: Nova Sonic 2.0** (`amazon.nova-2-sonic-v1:0`). Full demo loop completed successfully.

```
02:41:25 - Client connected
02:41:31 - Break DB: SG rule revoked
03:00:09 - Break DB: SG rule revoked
03:00:11 - Phase → DIAGNOSING, master agent starts
03:00:14 - assess_severity tool called
03:00:17 - activate_diagnosis tool called
03:00:21 - Diagnosis tools fire (check_network, check_health, pull_logs, check_recent_changes)
03:00:42 - Diagnosis complete (RCA: missing SG rule)
03:00:46 - activate_voice_call tool called (phase → CALLING)
03:00:54 - Master agent complete, voice session starts
03:00:55 - Twilio call placed (SID=CA908ec3d72640fdf066b51eddebb35035)
03:01:03 - Twilio Media Stream WebSocket connected
03:01:04 - Nova Sonic 2.0 session started
03:01:05 - sessionStart + promptStart + systemPrompt + audioContentStart + hello.pcm sent
03:01:05 - completionStart received (< 1s latency!)
03:01:05 - User speech transcribed: "hello."
03:01:06 - SPECULATIVE text: "This is the AI Operations Center. We have a critical Aurora database incident."
03:01:06 - Audio output starts (event #19)
03:01:08 - Turn 1 ended (intro)
03:01:11 - Turn 2 ended (connection pool info)
03:01:23 - Turn 3 ended
03:01:25 - Turn 4 ended
03:01:31 - Turn 5 ended
03:01:34 - Turn 6 ended
03:01:40 - authenticate_user tool called (passphrase: "aurorasunrise") → SUCCESS (word-level match)
03:01:41 - check_service_health tool called
03:01:45 - Turn 7 ended (health status report)
03:01:50 - Turn 8 ended
03:01:59 - restore_connectivity tool called (confirmation: "yes") → SG rule RESTORED
03:01:59 - Phase → RECOVERING
03:02:00 - Voice timeout reached → session stopped
03:02:00 - Phase → RESOLVED
03:02:02 - Phase → HEALTHY
03:03:04 - Twilio stop event (user hung up) → Nova Sonic session closed
```

**Key observations**:
- Nova Sonic 2.0 responded in < 1 second (vs 5s+ with v1)
- No watchdog needed — first attempt worked
- 1622 total events, 1194 audio outputs (~2 minutes of active voice)
- All 3 tools called successfully: authenticate_user → check_service_health → restore_connectivity
- Passphrase "aurorasunrise" matched via word-level fuzzy match
- SG rule restored successfully — full demo loop completed
- ~10s latency between user speech and agent response (UX issue, not a blocker)
- Voice timeout (90s) fired 1 second after restore_connectivity — very tight but worked

---

## What to Improve Next

1. **Reduce voice latency** (~10s delay between user speech and agent response). Investigate:
   - Nova Sonic end-of-turn detection settings
   - Audio chunk size / buffering in the Twilio bridge
   - Whether the reference samples have lower latency

2. **Voice timeout margin** — The timeout fired 1s after the tool completed. Consider either:
   - Increasing to 120s for extra safety
   - Or having `restore_connectivity` tool explicitly end the voice session after speaking confirmation

3. **Cosmetic**: Clean up `Unclosed client session` log noise

---

## Architecture Reference

```
User Phone ←→ Twilio (Media Stream) ←→ ECS WebSocket (/twilio/media-stream)
                                              ↕
                                    TwilioMediaStreamHandler
                                              ↕
                                      NovaSonicSession
                                              ↕
                              Bedrock Runtime (us-east-1)
                              amazon.nova-2-sonic-v1:0
                              Bidirectional HTTP/2 Stream
```

**Audio path**:
- Twilio → mulaw 8kHz → decode to PCM 8kHz → base64 → Nova Sonic audioInput
- Nova Sonic audioOutput → base64 → decode PCM 8kHz → encode mulaw → Twilio

**Event sequence for session setup**:
1. Open bidirectional stream (`invoke_model_with_bidirectional_stream`)
2. Send `sessionStart` (inferenceConfiguration: maxTokens=1024, topP=0.9, temp=0.7)
3. Send `promptStart` (audio output config: 8kHz PCM mono, voice="tiffany", tools=TOOL_SPECS)
4. Start response processing task
5. Send `contentStart` (TEXT, system prompt)
6. Send `textInput` (system prompt content, role=SYSTEM)
7. Send `contentEnd`
8. Send `contentStart` (AUDIO, 8kHz PCM mono input config)
9. Send `audioInput` (hello.pcm as base64)
10. Continue streaming user audio as `audioInput` events

**Watchdog**: If no `completionStart` event within 5s, tear down session and retry from step 1.

---

## Package Versions (requirements.txt)

```
fastapi==0.115.12
uvicorn[standard]==0.34.2
websockets==15.0.1
strands-agents>=1.40.0
strands-agents-builder>=0.1.0
boto3>=1.34.0
aws_sdk_bedrock_runtime>=0.6.0
smithy-aws-core>=0.6.0
smithy-aws-event-stream>=0.3.0
smithy-http>=0.4.0
aiohttp>=3.8.0
twilio>=9.0.0
pymysql>=1.1.0
```

---

## Config Values (ECS Environment)

| Variable | Value |
|----------|-------|
| NOVA_SONIC_MODEL_ID | `amazon.nova-2-sonic-v1:0` |
| NOVA_SONIC_REGION | `us-east-1` |
| TWILIO_CALLING_TIMEOUT | `90` |
| VOICE_PASSPHRASE | `REDACTED_PASSPHRASE` |
| VOICE_SESSION_TIMEOUT | `90` |
| RDS_SECURITY_GROUP_ID | `sg-XXXXXXXXXXXXXXXXX` |
| ECS_SECURITY_GROUP_ID | `sg-YYYYYYYYYYYYYYYYY` |
| DEFAULT_VOICE_MODE | `mode_b` |

---

## Reference Implementations

Located in `src_workspaces/references/`:
- `sample-amazon-nova-sonic-twilio-integration/` — TypeScript, same Twilio+Nova Sonic pattern
- `sample-sonic-cdk-agent/` — Python, direct bidirectional stream
- `sample-nova-sonic-websocket-agentcore/` — Uses Strands BidiAgent (higher-level abstraction)
- `sample-Nova-Sonic-AgentCore-Healthcare-Call-Center/` — Python, uses `amazon.nova-2-sonic-v1:0`
