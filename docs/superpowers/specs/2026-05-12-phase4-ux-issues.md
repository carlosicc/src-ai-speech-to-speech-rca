# Phase 4 UX Issues — Mode B Demo Experience

**Date**: 2026-05-12
**Status**: Open — needs fixing before Summit demo
**Priority**: High

---

## Issues Found During Live Testing

### Issue 1: Mode B still requests browser microphone

**Symptom**: User selects Mode B (Twilio phone call), but clicking "Start Mic" still activates the browser microphone and sends `audio_input` messages.

**Root Cause**: The DevPanel's "Start Mic" button is not gated by voice mode. It always calls `startAudioCapture()` regardless of whether Mode B or Mode C is selected. Mode B should not involve the browser mic at all — the audio comes from the phone.

**Fix**: 
- Disable "Start Mic" button when Mode B or A is selected
- Mode B should auto-trigger the call during CALLING phase (already done in `demo_controller._start_twilio_voice_session()`) without needing browser audio
- The `audio_input` WebSocket handler should ignore audio when mode is B/A

---

### Issue 2: `audio_input` bypasses auto-loop call safety

**Symptom**: Even though auto-loop correctly skips real calls in Mode B, sending `audio_input` from the browser triggers `_start_voice_session()` which reads `demo_state.voice_mode` and places a real Twilio call.

**Root Cause**: The `_start_voice_session()` in `websocket_server.py` is triggered by the first `audio_input` message. It doesn't check whether the current call originated from auto-loop or manual trigger — it just looks at `demo_state.voice_mode`.

**Fix**:
- `audio_input` handler should only start a voice session if `voice_mode == "mode_c"`
- For Mode B, the session is started by `demo_controller._start_twilio_voice_session()` — browser audio should be ignored entirely

---

### Issue 3: Race condition — demo resets while Twilio call is in flight

**Symptom**: The call was placed at `14:51:35`, but demo reset at `14:51:41` (6s later). Twilio Media Stream connected at `14:51:48` (13s later) — by then the demo was already in HEALTHY state. The call ran orphaned.

**Root Cause**: The demo controller's voice session timeout is too short when a Twilio call is in flight. It takes ~8-13s for: Twilio API → phone rings → callee picks up → Polly intro → Media Stream connects → Nova Sonic initializes.

**Fix**:
- When Mode B places a call, extend the CALLING phase timeout to accommodate Twilio latency (at least 30s before timeout)
- Or: don't start the voice session timeout timer until the Media Stream actually connects
- On reset: actively hang up any in-flight Twilio call via `twilio.calls(callSid).update(status='completed')`

---

### Issue 4: ~10 second delay before AI speaks on phone

**Symptom**: After picking up the phone, it takes ~10s before the AI agent greets.

**Breakdown of latency**:
- Twilio API call → phone rings: ~5-7s (network + telephony routing)
- Polly `<Say>` intro: ~3s
- Media Stream WebSocket connects: ~1s
- Nova Sonic session initialize: ~0.1s
- Initial silence + Nova Sonic generating greeting: ~2-3s

**Total**: ~12-15s from call placement to AI greeting

**Fixes to reduce latency**:
- Shorten or remove the Polly `<Say>` intro (saves 3s)
- Send the greeting text in the system prompt to make Nova Sonic speak immediately
- Pre-warm the Nova Sonic session before Twilio connects (start session on call placement, queue audio once Media Stream arrives)

---

### Issue 5: Diagnosis agent model ID invalid

**Log**: `The provided model identifier is invalid` for `ConverseStream`

**Root Cause**: The `BEDROCK_MODEL_ID` env var has value `eu.anthropic.claude-sonnet-4-6` but the full model ID should be `eu.anthropic.claude-sonnet-4-6-20250514-v1:0` (from cdk.json).

**Impact**: Diagnosis falls back to static RCA, which is fine for demo but means no live Bedrock-powered analysis.

**Fix**: Update the CDK env var to use the full model ID from `cdk.json` context: `eu.anthropic.claude-sonnet-4-6-20250514-v1:0`

---

### Issue 6: Voice mode buttons don't show active state

**Symptom**: Clicking Mode A/B/C buttons in the DevPanel doesn't visually stick — no highlight, no indication which mode is currently active. User can't tell which mode is selected.

**Root Cause**: The `.active` CSS class was added but isn't being applied correctly. The `voiceMode` state is local to `DevPanel` (`useState("mode_c")`) and doesn't sync with the backend's actual voice mode. On page reload or if the backend has a different mode, the UI won't reflect reality.

**Fix**:
- Sync voice mode state from backend (read from `system_status` WebSocket message on connect)
- Ensure the `.active` class visually persists on the selected button (verify CSS specificity)
- Make the active style more obvious (larger contrast, bold border, or filled background)

---

### Issue 7: All DevPanel buttons lack context — unclear what they do

**Symptom**: Buttons say "MODE A", "MODE B", "MODE C", "Auto: ON/OFF", "Reset" — the operator has no idea what each does without consulting documentation. "Auto" is particularly confusing (it controls whether incidents auto-trigger every 180s for passersby).

**Root Cause**: No tooltip, subtitle, or hint text on any button in the DevPanel.

**Fix**: Add a tooltip (`title` attribute) or subtitle to every button/section:

| Section | Button | Tooltip/Hint |
|---------|--------|-------------|
| VOICE MODE | MODE A | AgentCore + Twilio (managed agent, real phone call) |
| VOICE MODE | MODE B | Bedrock + Twilio (direct stream, real phone call) |
| VOICE MODE | MODE C | Bedrock + Browser (mic/speaker, no phone) |
| CONTROL | Reset | Stop current incident, return to HEALTHY |
| CONTROL | Auto: ON/OFF | Auto-trigger incidents every 3min for passersby |
| TRIGGER INCIDENT | (each service) | Manually start an incident on this service |
| VOICE (MODE C) | Start Mic | Activate browser microphone for voice conversation |
| PHONE | Set | Send phone number to backend for Twilio calls |

Implementation: use `title` attribute on each `<button>` — zero-effort, browser-native tooltip on hover. Example:
```tsx
<button title="Auto-trigger incidents every 3min for booth passersby">
  Auto: {autoAdvance ? "ON" : "OFF"}
</button>
```

---

## Summary of Required Changes

| # | Issue | Severity | File(s) |
|---|-------|----------|---------|
| 1 | Mic button active in Mode B | High | `DevPanel.tsx`, `audioHandler.ts` |
| 2 | `audio_input` bypasses call safety | High | `websocket_server.py` |
| 3 | Demo resets while call in flight | Medium | `demo_controller.py`, `twilio_handler.py` |
| 4 | 10s delay before AI speaks | Medium | `twilio_handler.py`, `nova_sonic_client.py` |
| 5 | Invalid model ID for diagnosis | Low | `stack_backend.py` or `cdk.json` |
| 6 | Voice mode buttons don't visually stick | High | `DevPanel.tsx`, `theme.css` |
| 7 | All buttons lack hints (what does Auto do?) | Medium | `DevPanel.tsx` |

---

## Prompt for Next Agent Session

```
Read @docs/superpowers/specs/2026-05-12-phase4-ux-issues.md — fix all 7 UX issues for the DevPanel and Mode B. Key changes: (1) disable browser mic in Mode B, (2) audio_input handler ignores when mode≠C, (3) extend CALLING timeout for Twilio latency + cancel orphaned calls on reset, (4) reduce call-to-greeting latency by pre-warming Nova Sonic and shortening Polly intro, (5) fix diagnosis model ID, (6) voice mode buttons must visually stay pressed/highlighted showing active selection, (7) add tooltip hints to ALL DevPanel buttons — mode buttons (A: AgentCore+Twilio, B: Bedrock+Twilio phone, C: Bedrock+Browser), Auto (auto-trigger incidents every 3min), Reset (stop incident, return healthy), Start Mic, Set phone, etc. Build frontend to src_backend/static/ before deploying. Deploy, test, fix, redeploy until all issues resolved.
```
