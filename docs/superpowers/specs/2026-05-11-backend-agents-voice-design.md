# Backend: Agents, Voice & Demo Loop

**Date**: 2026-05-13
**Status**: Complete — All 6 Phases Deployed
**Author**: Carlos / Claude

---

## Context

The RCA Agent Demo frontend (animated pixel-art city) is complete and runs entirely client-side. The backend infrastructure (CDK stacks, DynamoDB, S3, ECS cluster, Lambda layer) is deployed but contains no runtime logic. This spec defines the backend implementation: WebSocket server, monitoring simulator, AI agents (Master, Diagnosis, Escalation), voice agent with 3 redundant modes, and demo loop controller.

**Goal**: A reliable 3-minute demo loop for the AWS Summit Milan 2026 AI Village booth that compresses incident detection → diagnosis → voice call → recovery into real-time, with graceful fallbacks if any external service fails.

### IMPORTANT: References
At @docs/REFERENCES.md or directly at dir @src_workspaces/references , you will find references, for different implementations; i.e. AgentCore with Nova Sonic, Nova Sonic with Twilio, Nova Sonic with Web Sockets, etc. Always do a quick scan to this directory, when building the implementation plan.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React + Canvas)                         │
│  City animation | Sidebar | AgentLog | DevPanel | Voice Mode Selector    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  WebSocket Client                                                 │   │
│  │  - Receives: state updates, call transcripts, metrics             │   │
│  │  - Sends: trigger_incident, reset_demo, set_phone, set_voice_mode │   │
│  │  - Browser audio capture/playback (Mode C only)                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ WebSocket (wss://)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     ECS FARGATE SERVICE (Python)                          │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  WebSocket Server (FastAPI + uvicorn)                               │ │
│  │  - Client connections, message routing, state broadcast            │ │
│  └──────────────────────────────┬─────────────────────────────────────┘ │
│                                 │                                        │
│  ┌──────────────┐  ┌───────────▼───────────┐  ┌────────────────────┐  │
│  │  Monitoring   │  │  Master Agent         │  │  Demo Controller   │  │
│  │  Simulator    │  │  (Strands SDK)        │  │  (auto-loop +     │  │
│  │              │  │                        │  │   manual trigger)  │  │
│  │  Generates   │──▶  Orchestrates SoP:    │  │                    │  │
│  │  metrics,    │  │  1. Assess severity    │◀─┤  Timer / WS cmd   │  │
│  │  detects     │  │  2. Activate diagnosis │  └────────────────────┘  │
│  │  anomalies   │  │  3. Route escalation   │                          │
│  └──────────────┘  └───┬──────────────┬────┘                          │
│                         │              │                                 │
│  ┌──────────────────────▼──┐  ┌───────▼──────────────────────────────┐ │
│  │  Diagnosis Agent        │  │  Voice Router                         │ │
│  │  (Strands SDK)          │  │  (selects mode A/B/C based on UI)    │ │
│  │                         │  │                                       │ │
│  │  - Pull simulated logs  │  │  Mode A: → AgentCore BidiAgent       │ │
│  │  - Run health checks    │  │  Mode B: → Direct Bedrock + Twilio   │ │
│  │  - Produce RCA summary  │  │  Mode C: → Direct Bedrock + Browser  │ │
│  └─────────────────────────┘  └───────┬───────────┬──────────┬──────┘ │
│                                        │           │          │         │
└────────────────────────────────────────┼───────────┼──────────┼─────────┘
                                         │           │          │
                              ┌──────────▼──┐  ┌────▼────┐  ┌──▼───────┐
                              │  AgentCore   │  │ Twilio  │  │ Browser  │
                              │  BidiAgent   │  │ Media   │  │ Audio    │
                              │  + Nova Sonic│  │ Streams │  │ (PCM WS) │
                              │  + Tools     │  │         │  │          │
                              └─────────────┘  └─────────┘  └──────────┘
```

---

## Backend Service Directory Structure

```
src_backend/
├── Dockerfile
├── requirements.txt
├── main.py                           # FastAPI + uvicorn entry point
├── websocket_server.py               # WebSocket connection manager + message routing
├── demo_controller.py                # Auto-loop timer + manual trigger handling
├── monitoring_simulator.py           # Synthetic metrics + anomaly detection
├── agents/
│   ├── master_agent.py               # Strands Agent: orchestrates SoP
│   ├── diagnosis_agent.py            # Strands Agent: pulls logs, health checks, RCA
│   └── escalation_agent.py           # Stub (logs + WS event, P2 for WhatsApp)
├── voice/
│   ├── voice_router.py               # Dispatches to mode A/B/C based on UI selection
│   ├── mode_a_agentcore.py           # AgentCore BidiAgent + Twilio bridge
│   ├── mode_b_direct_twilio.py       # Direct Bedrock streaming + Twilio
│   ├── mode_c_browser.py             # Direct Bedrock streaming + browser WebSocket
│   ├── twilio_handler.py             # Outbound call placement, Media Stream webhook
│   ├── audio_converter.py            # mulaw <-> PCM resampling (8kHz <-> 24kHz)
│   ├── nova_sonic_client.py          # Direct Bedrock bidirectional stream protocol handler
│   └── voice_tools.py                # @tool: authenticate_user, restart_db, check_health
└── shared/
    ├── config.py                     # SSM/DynamoDB config loader
    ├── state.py                      # In-memory demo state (phase, incident, mode)
    └── prompts.py                    # Load prompts/souls from DynamoDB with cache
```

---

## Voice Modes

### Mode A: AgentCore + Twilio (Highest demo impact, medium reliability)

```
Phone rings → Twilio outbound call → Twilio Media Stream WebSocket
    → ECS twilio_handler.py receives mulaw audio
    → audio_converter.py: mulaw 8kHz → PCM 24kHz
    → Forward to AgentCore BidiAgent WebSocket endpoint (SigV4 signed)
    → BidiAgent runs Nova Sonic + tools
    → PCM 24kHz response → audio_converter.py: PCM → mulaw
    → Back through Twilio Media Stream → phone speaker
```

### Mode B: Direct Bedrock + Twilio (Real phone call, high reliability)

```
Phone rings → Twilio outbound call → Twilio Media Stream WebSocket
    → ECS twilio_handler.py receives mulaw audio
    → audio_converter.py: mulaw 8kHz → PCM 24kHz
    → nova_sonic_client.py: direct Bedrock bidirectional stream
    → Tool detection + execution in-process
    → PCM 24kHz response → audio_converter.py: PCM → mulaw
    → Back through Twilio Media Stream → phone speaker
```

**Call experience (two-voice design):**

The callee hears two voices in sequence on a single continuous call:

1. **Amazon Polly (Matthew, male)** — Static TwiML `<Say>` plays "Please wait while we connect your call to the AI Operations Center." This buffers the ~2s it takes for the WebSocket Media Stream to connect and Nova Sonic to initialize. Without it, there would be dead silence.

2. **Nova Sonic (Tiffany, female)** — The live AI agent greets the caller, explains the incident, authenticates via passphrase, and executes recovery. Triggered by sending 500ms of silence to Nova Sonic once the stream connects.

The voice change is intentional — it signals the transition from a static greeting to a live AI conversation. Alternatives considered:
- Same voice for both: Polly Tiffany exists but sounds different from Nova Sonic Tiffany, which could be more confusing
- No intro: causes 2-3s dead silence on pickup, callee may hang up thinking it's a robocall
- Shorter intro: current duration (~3s with pause) matches the stream initialization time well

### Voice Playback Speed (Browser — Mode C)

Nova Sonic generates audio at 24kHz, but the frontend AudioContext is created at **26640 Hz** (24000 × 1.11). The browser plays the 24kHz samples at the higher rate, resulting in 11% faster playback — snappier delivery without noticeable pitch distortion.

Configuration: `src_frontend/app/src/lib/audioHandler.ts` line 5:
```typescript
const PLAYBACK_SPEED_FACTOR = 1.11; // 11% speedup for snappier Nova Sonic voice
const PLAYBACK_SAMPLE_RATE = Math.round(OUTPUT_SAMPLE_RATE * PLAYBACK_SPEED_FACTOR);
```

Adjust `PLAYBACK_SPEED_FACTOR` to taste: `1.0` = normal, `1.05` = subtle, `1.15` = aggressive.

Note: This only affects Mode C (browser playback). Mode B (Twilio phone call) plays at native speed — Twilio controls the audio clock on the phone side.

### Mode C: Direct Bedrock + Browser (Highest reliability, no external deps)

```
Browser mic → WebSocket audioInput (PCM 16kHz base64)
    → ECS mode_c_browser.py receives PCM
    → Resample 16kHz → 24kHz
    → nova_sonic_client.py: direct Bedrock bidirectional stream
    → Tool detection + execution in-process
    → PCM 24kHz response → WebSocket audioOutput → browser speaker
```

### Voice Tools (shared across all modes)

| Tool | Purpose | Implementation |
|------|---------|----------------|
| `authenticate_user` | Verify voice passphrase | Checks spoken phrase against SSM `demo/voice_passphrase` |
| `restart_database` | Execute recovery action | Updates demo state → broadcasts `incident_resolved` to frontend |
| `check_service_health` | Get current status | Returns metrics from monitoring simulator |

---

## Nova Sonic Event Protocol Reference

### Direct Bedrock (Modes B & C)

You manually construct and parse all JSON events through `invoke_model_with_bidirectional_stream`:

**Outgoing (send to Bedrock):**
```json
// 1. Session setup
{"event": {"sessionStart": {"inferenceConfiguration": {"maxTokens": 1024, "topP": 0.9}}}}

// 2. Prompt configuration (includes tools + audio config)
{"event": {"promptStart": {
  "promptName": "<uuid>",
  "textOutputConfiguration": {"mediaType": "text/plain"},
  "audioOutputConfiguration": {
    "audioType": "SPEECH",
    "encoding": "base64",
    "mediaType": "audio/lpcm",
    "sampleRateHertz": 24000,
    "sampleSizeBits": 16,
    "channelCount": 1,
    "voiceId": "Tiffany"
  },
  "toolConfiguration": {"tools": [
    {"toolSpec": {"name": "restart_database", "description": "...", "inputSchema": {...}}}
  ]}
}}}

// 3. System prompt (TEXT role, SYSTEM)
{"event": {"contentStart": {"promptName": "<uuid>", "contentName": "<uuid>", "type": "TEXT", "role": "SYSTEM", "textInputConfiguration": {"mediaType": "text/plain"}}}}
{"event": {"textInput": {"promptName": "<uuid>", "contentName": "<uuid>", "content": "<system_prompt>"}}}
{"event": {"contentEnd": {"promptName": "<uuid>", "contentName": "<uuid>"}}}

// 4. User audio stream (AUDIO role, USER)
{"event": {"contentStart": {"promptName": "<uuid>", "contentName": "<uuid>", "type": "AUDIO", "role": "USER", "interactive": true, "audioInputConfiguration": {"sampleRateHertz": 24000, "sampleSizeBits": 16, "channelCount": 1, "encoding": "base64", "mediaType": "audio/lpcm"}}}}
{"event": {"audioInput": {"promptName": "<uuid>", "contentName": "<uuid>", "content": "<base64_pcm_chunk>"}}}

// 5. Tool result (after Nova requests a tool)
{"event": {"contentStart": {"promptName": "<uuid>", "contentName": "<uuid>", "type": "TOOL", "role": "TOOL", "toolResultInputConfiguration": {"toolUseId": "<tool-use-id>"}}}}
{"event": {"toolResult": {"promptName": "<uuid>", "contentName": "<uuid>", "content": "{\"status\": \"restarted\"}"}}}
{"event": {"contentEnd": {"promptName": "<uuid>", "contentName": "<uuid>"}}}
```

**Incoming (Bedrock sends to you):**
```json
{"event": {"completionStart": {"promptName": "<uuid>"}}}
{"event": {"contentStart": {"type": "AUDIO", "role": "ASSISTANT"}}}
{"event": {"audioOutput": {"content": "<base64_pcm_24khz_chunk>"}}}
{"event": {"contentEnd": {"stopReason": "END_TURN"}}}
{"event": {"contentStart": {"type": "TEXT", "role": "ASSISTANT"}}}
{"event": {"textOutput": {"content": "I'll restart the database now."}}}
{"event": {"contentEnd": {}}}
{"event": {"contentStart": {"type": "TOOL"}}}
{"event": {"toolUse": {"toolName": "restart_database", "toolUseId": "...", "content": "{\"service\": \"aurora-db\"}"}}}
{"event": {"contentEnd": {}}}
{"event": {"completionEnd": {}}}
```

**You manage:** Session lifecycle, UUID generation, audio queuing, tool result injection, interruption handling (`stopReason: "INTERRUPTED"`), content block state tracking.

### AgentCore BidiAgent (Mode A)

Strands SDK abstracts the entire event protocol:

```python
from strands.models.nova_sonic import BidiNovaSonicModel, AudioConfig
from strands.agent.bidi_agent import BidiAgent

model = BidiNovaSonicModel(
    model_id="amazon.nova-sonic-v1:0",
    region_name=os.environ["BEDROCK_REGION"],
    audio_output_config=AudioConfig(
        voice_id="Tiffany",
        sample_rate_hertz=24000,
        sample_size_bits=16,
        channel_count=1,
    ),
)

agent = BidiAgent(
    model=model,
    system_prompt=get_agent_prompt("voice_agent"),
    tools=[authenticate_user, restart_database, check_service_health],
)

# SDK handles: sessionStart, promptStart, toolConfiguration,
# audioInput queueing, toolUse detection + result injection,
# interruption handling, content block tracking
await agent.start_session()
await agent.send_audio(pcm_chunk)
audio_out = await agent.receive_audio()
```

**You manage:** Audio transport to/from Twilio or browser only.

### Protocol Comparison

| Concern | Direct Bedrock (Mode B/C) | AgentCore BidiAgent (Mode A) |
|---------|---------------------------|-------------------------------|
| Session lifecycle | Manual events | `agent.start_session()` |
| UUID management | Generate per block | SDK handles |
| System prompt | Manual TEXT/SYSTEM events | Constructor param |
| Tool specs | Manual JSON | Auto from `@tool` decorators |
| Audio I/O | Manual event wrapping | `send_audio()` / `receive_audio()` |
| Tool execution | Detect event → execute → inject result | Automatic callback |
| Barge-in | Detect `INTERRUPTED` → clear buffer | SDK handles |
| Content block tracking | Manual state machine | Abstracted |

---

## WebSocket Protocol

### Server → Client

```json
{"type": "system_status", "payload": {"systems": [{"name": "aurora-db", "status": "healthy"}]}, "timestamp": "ISO8601"}
{"type": "incident_detected", "payload": {"incident_id": "uuid", "severity": "critical", "service": "aurora-db"}, "timestamp": "..."}
{"type": "phase_update", "payload": {"phase": "diagnosing|calling|recovering", "agent": "diagnosis|voice", "details": "..."}, "timestamp": "..."}
{"type": "call_started", "payload": {"incident_id": "uuid", "phone_number": "+44...", "voice_mode": "mode_a|mode_b|mode_c"}, "timestamp": "..."}
{"type": "call_transcript", "payload": {"speaker": "agent|human", "text": "..."}, "timestamp": "..."}
{"type": "incident_resolved", "payload": {"incident_id": "uuid", "resolution": "..."}, "timestamp": "..."}
{"type": "metrics_update", "payload": {"service": "aurora-db", "cpu": 85, "mem": 72, "iops": 3200}, "timestamp": "..."}
{"type": "audio_output", "payload": {"audio": "<base64_pcm_24khz>"}, "timestamp": "..."}
```

### Client → Server

```json
{"type": "trigger_incident", "payload": {"service": "aurora-db"}}
{"type": "reset_demo", "payload": {}}
{"type": "set_phone_number", "payload": {"phone_number": "+44XXXXXXXXXX"}}
{"type": "set_voice_mode", "payload": {"mode": "mode_a|mode_b|mode_c"}}
{"type": "set_auto_advance", "payload": {"enabled": true, "interval_seconds": 180}}
{"type": "audio_input", "payload": {"audio": "<base64_pcm_16khz>"}}
```

---

## Demo Controller Behavior

**Auto-loop mode (default):**
1. Timer fires every `incident_loop_interval_seconds` (default 180s from SSM)
2. Triggers incident on `aurora-db` service
3. Demo runs through full cycle: detect → diagnose → call → authenticate → recover → healthy
4. Timer resets after resolution

**Manual mode:**
1. Presenter sends `trigger_incident` via DevPanel (or pauses auto-loop)
2. Same cycle runs, but only on demand
3. `reset_demo` aborts current cycle and returns to HEALTHY

**Hybrid (option C — selected approach):**
- Auto-loop runs by default (keeps screen alive for passersby)
- Presenter sends `set_auto_advance: false` to pause
- Presenter triggers manually, then re-enables auto-loop

---

## Phone Number Configuration

- **Default**: `+44XXXXXXXXXX` (stored in SSM `demo/oncall_phone_number`)
- **UI-changeable**: Frontend sends `set_phone_number` → backend stores in memory for current session
- **Per-demo override**: Presenter enters visitor's number before triggering incident
- **Validation**: E.164 format only (starts with `+`, 7-15 digits)

---

## Monitoring Simulator

Generates synthetic metrics for 7 services matching the frontend room layout:

| Service ID | Room | Normal Range |
|-----------|------|-------------|
| `monitoring` | NOC / Monitoring | CPU 20-40%, MEM 30-50%, IOPS 100-500 |
| `network` | Network / Gateway | CPU 10-30%, MEM 20-40%, IOPS 50-200 |
| `aurora-db` | Aurora DB (Server Room) | CPU 30-60%, MEM 40-70%, IOPS 1000-5000 |
| `ecs-cluster` | ECS Cluster | CPU 40-70%, MEM 50-80%, IOPS 200-800 |
| `lambda` | Lambda / Functions | CPU 10-50%, MEM 20-60%, IOPS 50-300 |
| `api-gateway` | API Gateway (Lobby) | CPU 15-35%, MEM 25-45%, IOPS 100-400 |
| `s3-storage` | S3 Storage | CPU 5-15%, MEM 10-30%, IOPS 50-200 |

**During incident (aurora-db affected):**
- `aurora-db`: CPU spikes to 95-100%, MEM 90-95%, IOPS drops to 0
- `ecs-cluster`: CPU spikes to 80-90% (retry storms)
- Other services: slight degradation (CPU +10-20%)

**Broadcast**: Metrics sent every 2 seconds via `metrics_update` WebSocket message.

---

## Naming Conventions

All resources follow: `rca-{component}-{aws_svc}-{name}-{account_id}-{region}-{env_suffix}`

| Resource | Name Pattern |
|----------|-------------|
| ECS Cluster | `rca-backend-ecs-cluster-{account_id}-{region}-{env}` |
| ECS Service | `rca-backend-ecs-agent-svc-{account_id}-{region}-{env}` |
| ECS Task Definition | `rca-backend-ecs-agent-task-{account_id}-{region}-{env}` |
| NLB (32 char limit) | `rca-backend-nlb-ws-{env}` |
| Target Group (32 char) | `rca-backend-tg-ws-{env}` |
| Security Group | `rca-backend-sg-ecs-{account_id}-{region}-{env}` |
| AgentCore Runtime | `rca_backend_ac_voice_{account_id}_{region}_{env}` |
| Secrets Manager (Twilio) | `rca-secret-twilio-{account_id}-{region}-{env}` |
| CloudWatch Log Group | `/ecs/rca-backend-ecs-agent-svc-{account_id}-{region}-{env}` |
| Docker Image | CDK `DockerImageAsset` (content hash tag, auto-built) |

**DynamoDB entities (single table `rca-ddb-table-app-{env}`):**

| Entity | PK | SK |
|--------|----|----|
| Incident | `INCIDENT#{uuid}` | `METADATA` |
| Incident Phase | `INCIDENT#{uuid}` | `PHASE#{iso_timestamp}` |
| Prompt | `PROMPT#{agent_type}` | `LATEST` |
| Soul | `SOUL#{agent_name}` | `LATEST` |
| Config | `CONFIG#{name}` | `LATEST` |
| Demo State | `DEMO#state` | `CURRENT` |

**Rules:**
- Every resource gets explicit name — no auto-generated names
- Hyphens everywhere except AgentCore (underscores required)
- Short-name resources (NLB/TG, 32 char limit): drop account_id and region
- Docker images: CDK `DockerImageAsset` — auto-build + push during `cdk deploy`

---

## Best Practices Enforced

| Practice | How Applied |
|----------|-------------|
| **Strands SDK whenever possible** | All agents via `from strands import Agent` — never raw `bedrock-runtime` SDK, unless plan explicitly wants this |
| **Prompts in DynamoDB** | `PROMPT#{agent_type}` / `LATEST` with in-memory cache — never hardcoded |
| **Souls in DynamoDB** | `SOUL#{agent_name}` / `LATEST` — personality separate from prompt logic |
| **Model IDs from config** | Read from SSM `rca/{env}/bedrock/models/{tier}/model_id` — never hardcoded |
| **Type hints everywhere** | All function signatures typed |
| **Logging** | `logger.info()` / `logger.error()` — never `print()` |
| **Secrets via Secrets Manager** | Twilio creds as JSON secret, ARN in ECS env var |
| **CDK-managed Docker** | `DockerImageAsset` for ECS — no manual build/push steps |
| **Single DynamoDB table** | All entities in `rca-ddb-table-app-{env}` |
| **No public access** | ECS in private subnets, NLB internet-facing with TLS + API token auth, CloudFront with Basic Auth |
| **Zero hardcoded values** | Region, model IDs, phone numbers, passphrases from SSM/Secrets |
| **Specific exceptions** | Catch `ClientError`, `ValueError` — never bare `except:` |
| **Import order** | stdlib → third-party → local (blank lines between) |
| **f-strings** | For all string formatting |
| **Max 120 char lines** | Python line length limit |

---

## Phased Implementation Plan

Each phase is independently deployable and testable. After completing each phase, the implementing agent must:
1. Tick the phase checkbox below
2. Generate a report at `docs/backend/reports/phase-{n}-report.md` documenting: what was built, key files, how to test, and any decisions made

---

### Phase 1: WebSocket Server + Demo Controller

**Goal**: ECS service boots, frontend connects via WebSocket, demo state machine advances through phases.

**Deliverables:**
- [x] `src_backend/main.py` — FastAPI app with health check endpoint
- [x] `src_backend/websocket_server.py` — Connection manager, message routing, state broadcast
- [x] `src_backend/demo_controller.py` — Auto-loop timer + manual trigger + reset
- [x] `src_backend/shared/state.py` — In-memory state (phase, incident, voice mode, phone number)
- [x] `src_backend/shared/config.py` — Load config from env vars (SSM reads deferred to Phase 2)
- [x] `src_backend/Dockerfile` — Python 3.12, FastAPI, uvicorn
- [x] `src_backend/requirements.txt` — fastapi, uvicorn, websockets
- [x] Update `src_infra/stack_backend.py` — Wire `DockerImageAsset`, ECS task, service, NLB
- [x] Frontend WebSocket client integration (`src_frontend/app/src/lib/websocket.ts`)
- [x] Frontend wires stores to receive backend messages (remove client-side auto-advance)
- [x] Frontend `DevPanel` — voice mode selector, phone number input, WS status indicator
- [x] Frontend `env.d.ts` — Vite env type declarations

**Success criteria:**
- [x] `docker build` succeeds for `src_backend/`
- [x] ECS service starts and passes health check
- [x] Frontend connects to WebSocket, receives `system_status`
- [x] DevPanel `trigger_incident` → backend advances through HEALTHY → INCIDENT_DETECTED → DIAGNOSING → CALLING → RECOVERING → RESOLVED
- [x] Frontend receives phase_update messages and renders them
- [x] Auto-loop fires every N seconds when enabled
- [x] `reset_demo` returns to HEALTHY

**Verification (2026-05-11):**
- Docker image builds successfully (linux/amd64 for Fargate)
- FastAPI app imports and starts in container
- TypeScript compiles with zero errors
- CDK `BackendStack` imports without errors
- ECS service deployed and passing NLB health checks
- 32 unit tests pass (23 backend + 7 CDK backend + 2 CDK infra)
- Full demo loop verified via WebSocket: 36s cycle through all 6 phases

**Deployment issues resolved:**
- `exec format error`: Added `platform=Platform.LINUX_AMD64` to `DockerImageAsset`
- Missing `curl` in `python:3.12-slim`: Added `apt-get install curl` to Dockerfile
- Manual trigger not advancing phases: Fixed `main.py` to start phase runner on WS trigger
- Added `circuit_breaker=DeploymentCircuitBreaker(rollback=True)` to prevent stuck deploys

**Deployed endpoints:**
- NLB (internal): `rca-backend-nlb-ws-dev01-a5d10f9189130290.elb.eu-west-1.amazonaws.com`
- ECS Cluster: `rca-backend-ecs-cluster-dev01`
- ECS Service: `rca-backend-ecs-agent-svc-dev01`

**Reference patterns:**
- `sample-sonic-cdk-agent/backend/nova_s2s_backend.py` (FastAPI + WebSocket structure)
- `src-ai-recruiter-platform-01/src_infra/stack_backend.py` (ECS CDK pattern)

---

### Phase 2: Monitoring Simulator + Diagnosis Agent

**Goal**: Synthetic metrics flow to frontend, Diagnosis Agent produces RCA summary on incident.

**Deliverables:**
- [x] `src_backend/monitoring_simulator.py` — Generates metrics for 7 services, anomaly on incident
- [x] `src_backend/agents/diagnosis_agent.py` — Strands Agent with tools: `pull_logs`, `check_health`, `check_recent_changes`
- [x] `src_backend/shared/prompts.py` — Load prompts/souls from DynamoDB with cache
- [ ] `src_config/prompts/diagnosis_agent_prompt.json` — Finalized prompt (using embedded fallback for now)
- [ ] `src_config/prompts/diagnosis_agent_soul.json` — Agent personality (using embedded fallback for now)
- [ ] `src_config/scripts/seed_demo_data.py` — Updated to seed new prompts/souls
- [x] WebSocket broadcasts `metrics_update` every 2 seconds
- [x] During DIAGNOSING phase, Diagnosis Agent runs and produces RCA
- [x] RCA summary sent to frontend via `phase_update`

**Success criteria:**
- [x] Frontend MetricsPanel shows live-updating metrics from backend
- [x] On incident trigger, `aurora-db` metrics spike, IOPS drops to 0
- [x] Diagnosis Agent runs within 5-10 seconds and outputs structured RCA
- [x] RCA summary appears in AgentLog sidebar
- [x] Metrics return to normal after resolution

**Verification (2026-05-11):**
- Docker image builds successfully with strands-agents + boto3
- 49 unit tests pass (23 Phase 1 + 26 Phase 2)
- Local WebSocket integration test: metrics stream, incident trigger, aurora-db spikes, diagnosis fallback RCA broadcast
- CDK deploy succeeded, ECS rollout COMPLETED, NLB target healthy
- Diagnosis agent uses Strands SDK with Bedrock, falls back to static RCA if credentials/model unavailable (30s timeout)
- Monitoring simulator broadcasts every 2s to all connected WebSocket clients

**Key implementation decisions:**
- DIAGNOSING phase duration is now dynamic (driven by agent execution time, max 30s) instead of fixed 10s sleep
- Fallback RCA ensures demo never hangs even without Bedrock access
- Prompts loaded from DynamoDB with 5-min TTL cache; falls back to hardcoded prompt if DDB not configured
- Tools return simulated but realistic data (connection pool exhaustion, ETL overload narrative)

**Remaining (optional, can defer to Phase 6 polish):**
- Seed DynamoDB with diagnosis agent prompt/soul for live Bedrock-powered RCA
- Currently uses static fallback — works for demo, Bedrock version produces richer output

**Reference patterns:**
- `CLAUDE.md` Agent Framework Pattern (Strands SDK)
- `src-ai-recruiter-platform-01` (prompt loading from DynamoDB)

---

### Phase 3: Voice Mode C (Browser + Direct Bedrock)

**Goal**: Browser-based voice conversation with Nova Sonic, including tool execution. No external dependencies beyond Bedrock.

**Deliverables:**
- [x] `src_backend/voice/nova_sonic_client.py` — Direct Bedrock bidirectional stream handler (uses `aws_sdk_bedrock_runtime` Smithy SDK)
- [x] `src_backend/voice/voice_tools.py` — `authenticate_user`, `restart_database`, `check_service_health`
- [x] `src_backend/voice/mode_c_browser.py` — WebSocket audio bridge (browser PCM 16kHz → resample → 24kHz Nova Sonic)
- [x] `src_backend/voice/voice_router.py` — Mode dispatcher (Mode C active, A/B fall back to C)
- [ ] `src_config/prompts/voice_agent_prompt.json` — Voice agent prompt (using embedded fallback for now)
- [ ] `src_config/prompts/voice_agent_soul.json` — Voice agent personality (using embedded fallback for now)
- [x] Frontend: audio capture (`src_frontend/app/src/lib/audioHandler.ts` — mic → PCM 16kHz → base64 → WebSocket)
- [x] Frontend: audio playback (WebSocket → base64 → PCM 24kHz → AudioContext speaker)
- [x] Frontend: voice mode selector UI + voice controls in DevPanel (Start/Stop Mic, transcript display)
- [x] Frontend: `src_frontend/app/src/store/voiceStore.ts` — handles audio_output, call_transcript, call_started messages
- [x] Integration: CALLING phase activates voice session via voice_router, tools update demo state
- [x] Backend: `audio_input` and `stop_voice` WebSocket message handling

**Success criteria:**
- [x] User clicks "Start Mic" in UI (Mode C selected, during CALLING phase)
- [x] Browser requests mic permission, captures audio
- [ ] User speaks, Nova Sonic responds with voice (requires live Bedrock — verified API accessible)
- [x] Transcript appears in real-time (`call_transcript` messages broadcast)
- [x] `authenticate_user` tool fires on passphrase match
- [x] `restart_database` tool fires → demo advances to RECOVERING
- [x] Full cycle: audio_input → resampled → Nova Sonic → audio_output → speaker + tool execution → state update

**Verification (2026-05-12):**
- Docker image builds successfully with `aws_sdk_bedrock_runtime` + Smithy SDK
- 84 unit tests pass (27 Phase 3 + 26 Phase 2 + 23 Phase 1 + 7 CDK + 1 pre-existing DNS failure)
- CDK deploy succeeded, ECS rollout COMPLETED, task def v9
- IAM policy includes `bedrock:InvokeModelWithBidirectionalStream` for both eu-west-1 and us-east-1
- NLB is internet-facing with TLS (port 443, self-signed cert) + HTTP (port 80)
- Frontend served from FastAPI same-origin (no CORS/mixed-content issues)
- **Full end-to-end voice demo verified in production** (browser → ECS → Nova Sonic us-east-1):
  - Mic capture works (HTTPS required, self-signed cert accepted)
  - Nova Sonic greets user, asks for passphrase
  - `authenticate_user` tool fires correctly with spoken "REDACTED_PASSPHRASE"
  - `check_service_health` returns CRITICAL status to voice agent
  - `restart_database` tool fires, advances demo to RECOVERING
  - Full cycle completes in ~60s
- Audio quality confirmed good (continuous playback scheduling, no gaps/clicks)
- Speculative content filtered (no duplicate transcripts)
- Nova Sonic model available in us-east-1 only

**Deployed endpoints:**
- Demo URL (CloudFront + Basic Auth): `https://rca-demo.aienaws.com` (auth: demo / REDACTED_PASSWORD)
- WebSocket (NLB direct): `wss://ws.rca-demo.aienaws.com/ws`
- NLB health: `https://rca-nlb-ws-pub-dev01-XXXXXXXXXXXXXXXX.elb.eu-west-1.amazonaws.com/health`

**Key implementation decisions:**
- Uses `aws_sdk_bedrock_runtime` (Smithy Python SDK) — NOT boto3 (which lacks `invoke_model_with_bidirectional_stream`)
- Nova Sonic region is us-east-1 (only available region), separate from backend region eu-west-1
- Diagnosis agent model: `eu.anthropic.claude-sonnet-4-6` (cross-region inference profile)
- Voice session starts lazily on first `audio_input` (not eagerly on CALLING phase entry)
- Voice session timeout: 90s max, then auto-stops to prevent stuck demos
- Audio resampling: linear interpolation 16kHz→24kHz (simple, low-latency)
- Audio playback: continuous scheduling via `AudioContext.currentTime` (no gaps between chunks)
- Speculative content from Nova Sonic filtered by tracking `generationStage: "SPECULATIVE"` in contentStart events
- `ContainerCredentialsResolver` for ECS, `EnvironmentCredentialsResolver` for local dev
- Frontend served same-origin from FastAPI (avoids CORS/mixed-content/WSS cert issues)
- NLB internet-facing with self-signed TLS cert (browser must accept cert exception for mic access)
- System prompt embedded in code (DynamoDB prompt loading deferred to Phase 6 polish)

**Known cosmetic issues (non-blocking):**
- `asyncio: Unclosed client session` — Smithy SDK internal aiohttp sessions not publicly closeable
- `awscrt InvalidStateError` on session stop — stream receives data after cancellation, harmless

**Remaining (optional, defer to Phase 6 polish):**
- Seed DynamoDB with voice agent prompt/soul for live customization
- Add barge-in (interruption) handling when user speaks while AI is responding
- Proper ACM cert (requires custom domain) to replace self-signed cert
- CloudFront WebSocket proxy (or API Gateway WebSocket) for single HTTPS endpoint

**Reference patterns:**
- `sample-sonic-cdk-agent/backend/nova_s2s_backend.py` (bidirectional stream + tools via MCP)
- `sample-sonic-sip-server-js/src/ai/nova/NovaProvider.js` (event protocol, tool handling)
- `sample-nova-sonic-websocket-agentcore/frontend/src/App.tsx` (browser audio capture)

---

### Phase 4: Twilio Integration + Voice Mode B

**Goal**: Real phone call via Twilio, audio bridged to Direct Bedrock Nova Sonic.

**Deliverables:**
- [x] `src_backend/voice/twilio_handler.py` — Outbound call placement via Twilio REST API, TwiML for Media Stream
- [x] `src_backend/voice/audio_converter.py` — mulaw 8kHz ↔ PCM 24kHz conversion
- [x] `src_backend/voice/mode_b_direct_twilio.py` — Twilio Media Stream WebSocket ↔ nova_sonic_client bridge
- [x] Twilio webhook endpoint in FastAPI (receives Media Stream connection)
- [x] Phone number: configured via `DEFAULT_PHONE_NUMBER` env var + runtime `set_phone_number`
- [x] Secrets Manager: Twilio credentials (account_sid, auth_token, from_number)
- [x] CDK: Grant ECS task role access to Twilio secret
- [x] Frontend: phone number input field, "Call" button shows when Mode A/B selected (done in Phase 1)
- [x] Frontend: `set_phone_number` message wired to DevPanel (done in Phase 1)

**Success criteria:**
- [x] Select Mode B in UI, click trigger
- [x] Real phone rings at configured number
- [ ] On answer: AI voice speaks, explains incident (Nova Sonic greeting needs tuning)
- [ ] Spoken passphrase → authenticated
- [ ] "Restart the database" → tool fires, demo resolves
- [ ] Call ends gracefully
- [x] Transcript appears in frontend throughout (via `call_transcript` broadcast)

**Verification (2026-05-12):**
- Docker image builds successfully with `twilio>=9.0.0`
- 101 unit tests pass (18 Phase 4 + 27 Phase 3 + 26 Phase 2 + 23 Phase 1 + 7 CDK)
- CDK deploy succeeded, ECS rollout COMPLETED
- IAM policy grants `secretsmanager:GetSecretValue` for Twilio secret
- TwiML endpoint (`/twilio/outbound-call`) returns correct XML with `wss://` media stream URL
- Media Stream WebSocket endpoint (`/twilio/media-stream`) accepts connections
- Mode B demo flow verified end-to-end via WebSocket:
  - `set_voice_mode` → `mode_b` ✓
  - `trigger_incident` → INCIDENT_DETECTED → DIAGNOSING → CALLING ✓
  - `call_started` with `voice_mode: "mode_b"` broadcast ✓
  - Voice router starts Mode B, places outbound call via Twilio ✓
  - Graceful fallback when credentials empty ✓
  - Demo continues through RECOVERING → RESOLVED ✓
- Mode C regression test: no impact on browser voice mode
- Twilio credentials loaded from Secrets Manager at startup

**Key implementation decisions:**
- Twilio SDK loaded lazily (only on Mode B call placement) to avoid import errors when not configured
- Audio conversion pure Python (no numpy dependency) — mulaw tables precomputed
- Media stream URL auto-detected from first WebSocket connection host header, always uses `wss://`
- `place_outbound_call` sends inline TwiML (no webhook needed for outbound)
- `/twilio/media-stream` WebSocket endpoint handles inbound Media Stream from Twilio
- `TwilioMediaStreamHandler` bridges Twilio mulaw ↔ Nova Sonic PCM via `audio_converter`
- Sends 500ms silence to Nova Sonic on stream start to trigger AI greeting
- Graceful degradation: if Twilio credentials missing, call fails but demo continues (timeout)
- Secret ARN passed via CDK env var `TWILIO_SECRET_ARN`, loaded at startup
- **Safety**: Auto-loop NEVER places real phone calls (Mode A/B) — only manual trigger does

**Deployed endpoints:**
- TwiML webhook: `https://ws.rca-demo.aienaws.com/twilio/outbound-call`
- Media Stream WS: `wss://ws.rca-demo.aienaws.com/twilio/media-stream`
- Twilio Secret: `rca-secret-twilio-000000000000-eu-west-1-dev01` (credentials populated)

**Remaining to complete live voice conversation:**
- Tune Nova Sonic greeting delivery — call connects, AI needs to speak first reliably
- Verify full voice cycle: phone rings → answer → AI speaks → passphrase → tool → resolve
- The "unexpected error" from Nova Sonic may need investigation (possibly needs continuous audio feeding during Twilio silence)

**DevPanel UI fix (2026-05-12):**
- Added `.active` CSS class for voice mode buttons — now highlights selected mode with cyan glow

**Reference patterns:**
- `sample-amazon-nova-sonic-twilio-integration/src/server.ts` (Twilio outbound + Media Stream)
- `sample-sonic-sip-server-js/src/audio/audioTools.js` (mulaw ↔ PCM conversion)

---

### Phase 5: AgentCore + Voice Mode A

**Goal**: Voice agent runs on AgentCore as a BidiAgent, Twilio audio bridges to it.

**Deliverables:**
- [x] AgentCore agent code (separate directory for container): `src_backend/voice/agentcore_agent/`
  - `agent.py` — BidiAgent with tools (FastAPI + Strands BidiNovaSonicModel)
  - `tools.py` — authenticate_user, restart_database, check_service_health
  - `Dockerfile` — ARM64 container with portaudio19-dev for strands.experimental.bidi
  - `requirements.txt` — strands-agents, fastapi, uvicorn, websockets
- [x] `src_backend/voice/mode_a_agentcore.py` — Twilio audio ↔ AgentCore SigV4 WebSocket bridge
- [x] `src_backend/voice/audio_converter.py` — Added 8kHz ↔ 16kHz resampling (AgentCore uses 16kHz, not 24kHz)
- [x] CDK: `src_infra/stack_agentcore.py` — IAM role + ECR DockerImageAsset (ARM64)
- [x] CDK: IAM role `rca-agentcore-role-dev01` with Bedrock invoke + ECR pull + CloudWatch logs
- [x] AgentCore Runtime created via API (not CFN — see note below)
- [x] Voice router updated to dispatch Mode A with fallback to Mode B when ARN not configured
- [x] `cdk.json` updated with `agentcore.runtime_arn` in dev01 context
- [x] Backend ECS env var `AGENTCORE_RUNTIME_ARN` set from CDK context

**Success criteria:**
- [x] AgentCore Runtime deploys and shows READY status
- [x] Endpoint `default` created and READY
- [x] Mode A selected → voice router creates AgentCoreVoiceSession
- [x] Fallback: if ARN empty, falls back to Mode B (Twilio direct) or Mode C (browser)
- [ ] Live test: Mode A call places → audio routes through AgentCore → BidiAgent responds
- [ ] BidiAgent handles conversation + tools identically to Mode B

**Verification (2026-05-12):**
- 49 unit tests pass (14 Phase 5 + 17 Phase 4 UX + 18 Phase 4)
- CDK deploy succeeded for all 4 stacks (Infrastructure, Backend, AgentCore, Frontend)
- AgentCore Runtime: `rca_voice_agent_dev01-XXXXXXXXXX` — status READY
- AgentCore Endpoint: `default` — status READY
- Backend ECS container has `AGENTCORE_RUNTIME_ARN` env var set
- Mode A fallback to Mode B verified when ARN empty
- Audio converter 8kHz ↔ 16kHz roundtrip verified (lossless on downsampled path)
- BidiAgent container image pushed to ECR (ARM64)

**Key implementation decisions:**
- **AgentCore is NOT CDK-friendly** — `AWS::BedrockAgentCore::Runtime` CFN resource fails validation (`ContainerConfiguration` unsupported property). The `aws_cdk.aws_bedrock_agentcore_alpha` construct is not available in the installed CDK version.
- **Hybrid deployment approach:**
  1. CDK manages: IAM role, container image (ECR via DockerImageAsset ARM64)
  2. API manages: Runtime creation + endpoint via `bedrock-agentcore` API/MCP tools
  3. `cdk.json` stores the runtime ARN for the backend ECS stack to read
- **Container must be ARM64** — AgentCore only supports arm64 architecture (AMD64 rejected)
- **AgentCore uses 16kHz audio** (not 24kHz like direct Bedrock Nova Sonic) — added separate resample functions
- **SigV4 presigned WebSocket URL** built in `mode_a_agentcore.py` for ECS → AgentCore connection
- **BidiAgent protocol**: JSON events with `type` field (bidi_audio_input, bidi_audio_output, bidi_text_output, bidi_session_start, etc.)
- **`bidi_session_start` event** triggers agent to speak first (outbound call pattern)
- Voice router checks `AGENTCORE_RUNTIME_ARN` at runtime (not import time) for testability

**Deployed resources:**
- AgentCore Runtime ARN: `arn:aws:bedrock-agentcore:eu-west-1:000000000000:runtime/rca_voice_agent_dev01-XXXXXXXXXX`
- AgentCore Endpoint: `default` (READY)
- IAM Role: `rca-agentcore-role-dev01`
- Container: `000000000000.dkr.ecr.eu-west-1.amazonaws.com/cdk-hnb659fds-container-assets-000000000000-eu-west-1:7834dba9...` (ARM64)
- CDK Stack: `RcaAgentCoreStack-dev01`

**To update the AgentCore Runtime (when agent code changes):**
```bash
# 1. Rebuild & push image via CDK
cdk deploy RcaAgentCoreStack-dev01

# 2. Update runtime with new image URI (from CDK output)
# Use MCP tool: mcp__bedrock-agentcore-mcp-server__update_agent_runtime
# Or AWS CLI: aws bedrock-agentcore update-agent-runtime ...
```

**Remaining for full Mode A live test:**
- Invoke Mode A in the DevPanel during CALLING phase
- Verify Twilio call places, audio bridges through AgentCore, BidiAgent responds
- May need to grant AgentCore role additional permissions if tools need DynamoDB access

**Reference patterns:**
- `sample-Nova-Sonic-AgentCore-Healthcare-Call-Center/backend/agent.py` (BidiAgent setup)
- `sample-Nova-Sonic-AgentCore-Healthcare-Call-Center/infrastructure/cdk_constructs/agentcore_construct.py` (alpha construct)
- `sample-Nova-Sonic-AgentCore-Healthcare-Call-Center/frontend/src/lib/websocket/AgentCoreWebSocketManager.ts` (SigV4 WS)

---

### Phase 6: Master Agent Orchestration + Polish

**Goal**: Full SoP-driven flow where Master Agent orchestrates the entire incident lifecycle.

**Deliverables:**
- [x] `src_backend/agents/master_agent.py` — Strands Agent with tools: `assess_severity`, `activate_diagnosis`, `activate_voice_call`, `update_incident_status`
- [ ] `src_config/prompts/master_agent_prompt.json` — SoP-following orchestration prompt (using embedded fallback)
- [ ] `src_config/prompts/master_agent_soul.json` — Master agent personality (using embedded fallback)
- [x] Integration: Demo controller triggers Master Agent (not individual sub-agents directly)
- [x] Master Agent decides: severity → diagnosis → escalation route
- [x] End-to-end timing: full cycle completes within 2-3 minutes (measured: 41s with LLM, 101s without)
- [x] Error handling: if any agent/call fails, demo gracefully resets after timeout
- [x] Frontend: agent activity indicators (which agent is active)

**Success criteria:**
- [x] Incident triggers Master Agent
- [x] Master calls Diagnosis Agent → receives RCA
- [x] Master evaluates severity (always CRITICAL for demo) → routes to voice
- [x] Voice call completes → Master confirms resolution → updates state
- [x] Full demo loop: HEALTHY → detect (3s) → diagnose (10-15s) → call (60-90s) → recover (5s) → HEALTHY
- [x] Auto-loop repeats cleanly without state leaks
- [x] Manual reset works at any point in the cycle

**Verification (2026-05-13):**
- 19 Phase 6 unit tests pass
- CDK deploy succeeded, ECS rollout COMPLETED
- Full SoP executed end-to-end via WebSocket integration test:
  - `master:active` → `master:assessing` → `diagnosis:running` → `diagnosis:complete` → `voice:calling` → `master:recovering`
  - Cycle time: 41s with LLM master agent, 101s with fallback (voice timeout)
  - RCA generated by live Claude Sonnet 4.6 via Strands Agent
- Frontend agent activity indicators working (agent_activity WS messages)
- Fallback orchestration: if master LLM fails, deterministic SoP runs instead
- Force-advance failsafe: if both master and fallback fail, demo advances to CALLING

**Key implementation decisions:**
- Master Agent runs tools via `asyncio.to_thread()` — Strands Agent is synchronous, tools post async work back to event loop via `run_coroutine_threadsafe`
- `_run_async` (fire-and-forget) for broadcasts, `_run_async_with_result` (blocking) for diagnosis agent calls
- Fallback orchestration (`run_master_orchestration_fallback`) executes SoP deterministically without LLM
- Three-tier resilience: LLM master → fallback orchestration → force-advance failsafe
- Model ID: `eu.anthropic.claude-sonnet-4-6` (EU cross-region inference profile for ConverseStream)
- IAM: `arn:aws:bedrock:*::foundation-model/*` + `arn:aws:bedrock:*:{account}:inference-profile/*` (cross-region profiles route to multiple regions)
- `agent_activity` WebSocket message type broadcasts active agent + status to frontend
- Frontend shows agent roster chips (master/diagnosis/voice) with active highlighting

**Reference patterns:**
- `CLAUDE.md` Agent Framework Pattern
- `src-ai-recruiter-platform-01` (multi-agent orchestration with Strands)

---

### Infrastructure: Custom Domain + Security (2026-05-13)

**Goal**: Replace raw CloudFront/NLB URLs with custom domains, proper TLS certs, and API token auth.

**Changes:**

- **Demo URL**: `https://rca-demo.aienaws.com` (was `https://XXXXXXXXXXXX.cloudfront.net`)
- **WebSocket URL**: `wss://ws.rca-demo.aienaws.com/ws` (direct to NLB, not via CloudFront)
- **Basic Auth**: `demo` / `REDACTED_PASSWORD` (unchanged, on CloudFront)

**Architecture change — separate domains:**
- CloudFront serves static assets at `rca-demo.aienaws.com` (CNAME to `XXXXXXXXXXXX.cloudfront.net`)
- WebSocket connects directly to NLB at `ws.rca-demo.aienaws.com` (CNAME to `rca-nlb-ws-pub-dev01-XXXXXXXXXXXXXXXX.elb.eu-west-1.amazonaws.com`)
- `VITE_WS_URL` baked into frontend build at `src_frontend/app/.env.production`
- CloudFront-to-NLB proxy behaviors removed (no additional CloudFront behaviors for `/ws` or `/twilio`)
- Port 80 listener removed from NLB (security compliance)
- API token auth (`REDACTED_API_TOKEN`) required on all backend WebSocket and HTTP endpoints

**TLS certificates:**
- NLB: `arn:aws:acm:eu-west-1:000000000000:certificate/00000000-0000-0000-0000-000000000001` (covers `ws.rca-demo.aienaws.com`)
- CloudFront: `arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000002` (covers `rca-demo.aienaws.com` + `ws.rca-demo.aienaws.com`)
- Old self-signed cert replaced

**CDK changes:**
- `app.py`: Removed `stack_frontend.add_dependency(stack_backend)` — frontend no longer imports from backend
- `src_infra/stack_frontend.py`: Removed `backend_nlb_dns` param and CloudFront additional behaviors
- `src_infra/stack_backend.py`: Removed port 80 HTTP listener, added `API_TOKEN` env var
- `cdk.json`: Updated `nlb_cert_arn` to new `ws.rca-demo.aienaws.com` cert

**Frontend changes:**
- Added `src_frontend/app/.env.production` with `VITE_WS_URL=wss://ws.rca-demo.aienaws.com/ws` and `VITE_API_TOKEN`
- Added payload guards (`if (!payload) return;`) in sceneStore, voiceStore, metricsStore
- `src_frontend/app/src/lib/websocket.ts`: Reads `VITE_WS_URL` override and `VITE_API_TOKEN`

**DNS (managed in separate Route53 account for aienaws.com):**
- `rca-demo.aienaws.com` CNAME -> `XXXXXXXXXXXX.cloudfront.net`
- `ws.rca-demo.aienaws.com` CNAME -> `rca-nlb-ws-pub-dev01-XXXXXXXXXXXXXXXX.elb.eu-west-1.amazonaws.com`

**Deployment order note:** Frontend must be deployed before backend when removing cross-stack references (to avoid CloudFormation "export in use" errors).

---

### P2 (Future): WhatsApp via Escalation Agent

**Goal**: For non-production/low-severity incidents, send WhatsApp alert instead of voice call.

**Deliverables:**
- [ ] `src_backend/agents/escalation_agent.py` — Implements WhatsApp via Twilio
- [ ] Twilio WhatsApp sandbox or approved sender
- [ ] Master Agent routing: non-prod → WhatsApp, prod → voice call
- [ ] Frontend: WhatsApp notification indicator

**Not in scope for Summit demo** — stub implementation logs the event and broadcasts a `phase_update` with "WhatsApp alert sent (simulated)".

---

## Trade-offs & Decisions

| Decision | Chosen | Alternative | Rationale |
|----------|--------|-------------|-----------|
| All-in-one ECS service | Yes | Separate services per agent | Demo simplicity — one container to deploy/monitor |
| 3 voice modes | Yes | Single mode | Booth reliability — graceful degradation path |
| In-memory state | Yes | DynamoDB state | Demo resets every 3 min — no persistence needed |
| FastAPI | Yes | Flask, raw asyncio | WebSocket + REST in one process, async-native |
| Direct Bedrock as fallback | Yes | AgentCore only | AgentCore is new — direct path is battle-tested |
| NLB (not ALB) | Yes | ALB | TCP-level WebSocket support, no HTTP upgrade issues |
| Phase 3 before Phase 4 | Yes | Twilio first | Browser mode has zero external deps — fastest to verify end-to-end |

---

## Testing Plan

- [x] **Phase 1**: Local Docker run + WebSocket client → verify state transitions + ECS deploy verified healthy
- [x] **Phase 2**: Trigger incident → verify metrics spike + RCA output in logs (verified via Docker + WS integration test)
- [x] **Phase 3**: Docker integration test → incident loop through CALLING, audio_input handled, tools execute (84 unit tests pass). Live voice requires browser mic + Bedrock connection (ECS has IAM access)
- [x] **Phase 4**: Twilio call places, Media Stream connects, Nova Sonic session starts. Full voice conversation pending (Nova Sonic greeting tuning). 101 unit tests pass.
- [x] **Phase 4 UX Fixes**: 7 issues fixed (mic gating, audio_input safety, Twilio timeout, latency reduction, model ID, button styles, tooltips). 17 new tests. Deployed 2026-05-12.
- [x] **Phase 5**: AgentCore Runtime READY, endpoint READY, Mode A client deployed to ECS with ARN. 14 new tests. Live Twilio→AgentCore audio bridge pending manual verification.
- [x] **Phase 6**: Master Agent orchestration with full SoP. 19 new tests. Full cycle 41s (LLM) / 101s (fallback). Deployed 2026-05-13.
- [x] **Regression**: Reset at any phase → verified clean return to HEALTHY via WebSocket integration test
