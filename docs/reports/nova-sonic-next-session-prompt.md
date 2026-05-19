# Prompt for Next Session: Fix Nova Sonic Voice Call

## Context

I'm building a demo for AWS Summit Milan. The demo has an AI Operations Center that detects a database incident, diagnoses it, and places a phone call to the on-call DBA via Twilio + Amazon Nova Sonic (speech-to-speech model). The DBA authenticates by voice passphrase, authorizes recovery, and the system restores the database.

The Twilio call connects fine, the WebSocket stream works, but **Nova Sonic intermittently fails to produce any audio output**. It worked exactly ONCE out of ~10 attempts in the previous session. When it worked, it was perfect (full conversation, tool use, 1346 audio chunks). Every other time, Nova Sonic accepts the session, acknowledges input via `usageEvent`, then goes completely silent.

## The Problem

Read `docs/nova-sonic-troubleshooting-report.md` for full details of what was tested. The key facts:

1. **Model:** `amazon.nova-sonic-v1:0` in `us-east-1`
2. **SDK:** `aws_sdk_bedrock_runtime==0.1.1` (Python experimental Smithy SDK)
3. **Audio:** 8kHz PCM 16-bit (matching Twilio's native rate, no resampling)
4. **Failure pattern:** 4 `usageEvent`s (system prompt + initial audio acknowledged), then nothing
5. **Success pattern (once):** After the 4 initial events, model continues with `completionStart`, ASR transcriptions, `audioOutput` events

## My Top Hypothesis

The `_send_initial_audio()` method in `src_backend/voice/twilio_handler.py` blocks for 2 seconds sending silence in a loop with `asyncio.sleep(0.032)`. During this time, Twilio's incoming audio is queued (not forwarded to Nova Sonic). When the loop finishes, ~100 audio chunks dump into Nova Sonic at once. This burst likely confuses the model's turn-detection.

**The official AWS sample** (`src_workspaces/references/sample-amazon-nova-sonic-twilio-integration/`) sends a pre-recorded `hello.pcm` file as a single instant write, then immediately starts forwarding live Twilio audio in real-time. No blocking loop, no sleep.

## What I Want You to Do

1. **Read the troubleshooting report** at `docs/nova-sonic-troubleshooting-report.md`
2. **Study the official AWS Twilio+Nova Sonic sample** at `src_workspaces/references/sample-amazon-nova-sonic-twilio-integration/src/` — specifically `server.ts` and `nova-client.ts` to understand their exact flow
3. **Fix `_send_initial_audio()`** — use the `hello.pcm` file from the sample's `assets/` directory (copy it to our backend), send it as a single instant burst, and ensure Twilio media forwarding is NOT blocked
4. **Consider running initial audio in a background task** so the `handle()` loop can immediately process incoming Twilio media events
5. **Deploy and test** — use `cdk deploy RcaBackendStack-dev01 --require-approval never`
6. **If it still fails**, add a retry mechanism: if no `completionStart` event arrives within 5 seconds of session start, tear down and restart the Nova Sonic session

## Key Files

- `src_backend/voice/nova_sonic_client.py` — Nova Sonic bidirectional stream client
- `src_backend/voice/twilio_handler.py` — Twilio Media Stream handler + audio bridge
- `src_backend/voice/audio_converter.py` — mulaw ↔ PCM conversion (no resampling needed at 8kHz)
- `src_backend/voice/voice_tools.py` — Tool specs for Nova Sonic (authenticate, restore, health check)
- `src_workspaces/references/sample-amazon-nova-sonic-twilio-integration/` — Official working sample
- `src_workspaces/references/sample-amazon-nova-sonic-twilio-integration/assets/hello.pcm` — Pre-recorded hello audio

## Constraints

- Don't change the SDK version (stay on 0.1.1 — 0.6.0 was tested and broke things)
- Don't add `turnDetectionConfiguration` (not supported by Nova Sonic v1)
- Keep `voiceId: "tiffany"` (the one successful run used this)
- Keep audio at 8kHz (matches Twilio native, no resampling)
- Follow all rules in CLAUDE.md (CDK for infra, no hardcoded prompts in prod, etc.)
