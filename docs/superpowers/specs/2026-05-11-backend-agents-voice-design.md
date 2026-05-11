# Backend: Agents, Voice & Demo Loop

**Date**: 2026-05-11
**Status**: Draft
**Author**: Carlos / Claude

---

## Context

The RCA Agent Demo frontend (animated pixel-art city) is complete and runs entirely client-side. The backend infrastructure (CDK stacks, DynamoDB, S3, ECS cluster, Lambda layer) is deployed but contains no runtime logic. This spec defines the backend implementation: WebSocket server, monitoring simulator, AI agents (Master, Diagnosis, Escalation), voice agent with 3 redundant modes, and demo loop controller.

**Goal**: A reliable 3-minute demo loop for the AWS Summit Milan 2026 AI Village booth that compresses incident detection → diagnosis → voice call → recovery into real-time, with graceful fallbacks if any external service fails.

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
| **Strands SDK only** | All agents via `from strands import Agent` — never raw `bedrock-runtime` SDK |
| **Prompts in DynamoDB** | `PROMPT#{agent_type}` / `LATEST` with in-memory cache — never hardcoded |
| **Souls in DynamoDB** | `SOUL#{agent_name}` / `LATEST` — personality separate from prompt logic |
| **Model IDs from config** | Read from SSM `rca/{env}/bedrock/models/{tier}/model_id` — never hardcoded |
| **Type hints everywhere** | All function signatures typed |
| **Logging** | `logger.info()` / `logger.error()` — never `print()` |
| **Secrets via Secrets Manager** | Twilio creds as JSON secret, ARN in ECS env var |
| **CDK-managed Docker** | `DockerImageAsset` for ECS — no manual build/push steps |
| **Single DynamoDB table** | All entities in `rca-ddb-table-app-{env}` |
| **No public access** | ECS in private subnets, NLB internal, CloudFront fronts everything |
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
- [ ] `src_backend/main.py` — FastAPI app with health check endpoint
- [ ] `src_backend/websocket_server.py` — Connection manager, message routing, state broadcast
- [ ] `src_backend/demo_controller.py` — Auto-loop timer + manual trigger + reset
- [ ] `src_backend/shared/state.py` — In-memory state (phase, incident, voice mode, phone number)
- [ ] `src_backend/shared/config.py` — Load config from env vars (SSM reads deferred to Phase 2)
- [ ] `src_backend/Dockerfile` — Python 3.12, FastAPI, uvicorn
- [ ] `src_backend/requirements.txt` — fastapi, uvicorn, websockets
- [ ] Update `src_infra/stack_backend.py` — Wire `DockerImageAsset`, ECS task, service
- [ ] Frontend WebSocket client integration (`src_frontend/app/src/lib/websocket.ts`)
- [ ] Frontend wires stores to receive backend messages (remove client-side auto-advance)

**Success criteria:**
- `docker build` succeeds for `src_backend/`
- ECS service starts and passes health check
- Frontend connects to WebSocket, receives `system_status`
- DevPanel `trigger_incident` → backend advances through HEALTHY → INCIDENT_DETECTED → DIAGNOSING → CALLING → RECOVERING → RESOLVED
- Frontend receives phase_update messages and renders them
- Auto-loop fires every N seconds when enabled
- `reset_demo` returns to HEALTHY

**Reference patterns:**
- `sample-sonic-cdk-agent/backend/nova_s2s_backend.py` (FastAPI + WebSocket structure)
- `src-ai-recruiter-platform-01/src_infra/stack_backend.py` (ECS CDK pattern)

---

### Phase 2: Monitoring Simulator + Diagnosis Agent

**Goal**: Synthetic metrics flow to frontend, Diagnosis Agent produces RCA summary on incident.

**Deliverables:**
- [ ] `src_backend/monitoring_simulator.py` — Generates metrics for 7 services, anomaly on incident
- [ ] `src_backend/agents/diagnosis_agent.py` — Strands Agent with tools: `pull_logs`, `check_health`, `check_recent_changes`
- [ ] `src_backend/shared/prompts.py` — Load prompts/souls from DynamoDB with cache
- [ ] `src_config/prompts/diagnosis_agent_prompt.json` — Finalized prompt
- [ ] `src_config/prompts/diagnosis_agent_soul.json` — Agent personality
- [ ] `src_config/scripts/seed_demo_data.py` — Updated to seed new prompts/souls
- [ ] WebSocket broadcasts `metrics_update` every 2 seconds
- [ ] During DIAGNOSING phase, Diagnosis Agent runs and produces RCA
- [ ] RCA summary sent to frontend via `phase_update`

**Success criteria:**
- Frontend MetricsPanel shows live-updating metrics from backend
- On incident trigger, `aurora-db` metrics spike, IOPS drops to 0
- Diagnosis Agent runs within 5-10 seconds and outputs structured RCA
- RCA summary appears in AgentLog sidebar
- Metrics return to normal after resolution

**Reference patterns:**
- `CLAUDE.md` Agent Framework Pattern (Strands SDK)
- `src-ai-recruiter-platform-01` (prompt loading from DynamoDB)

---

### Phase 3: Voice Mode C (Browser + Direct Bedrock)

**Goal**: Browser-based voice conversation with Nova Sonic, including tool execution. No external dependencies beyond Bedrock.

**Deliverables:**
- [ ] `src_backend/voice/nova_sonic_client.py` — Direct Bedrock bidirectional stream handler (~200-300 lines)
- [ ] `src_backend/voice/voice_tools.py` — `authenticate_user`, `restart_database`, `check_service_health`
- [ ] `src_backend/voice/mode_c_browser.py` — WebSocket audio bridge (browser PCM ↔ Nova Sonic)
- [ ] `src_backend/voice/voice_router.py` — Mode dispatcher (only Mode C active initially)
- [ ] `src_config/prompts/voice_agent_prompt.json` — Voice agent prompt
- [ ] `src_config/prompts/voice_agent_soul.json` — Voice agent personality
- [ ] Frontend: audio capture (mic → PCM 16kHz → base64 → WebSocket)
- [ ] Frontend: audio playback (WebSocket → base64 → PCM 24kHz → speaker)
- [ ] Frontend: voice mode selector UI (dropdown/toggle in DevPanel)
- [ ] Integration: CALLING phase activates voice session, tools update demo state

**Success criteria:**
- User clicks "Start Call" in UI (Mode C selected)
- Browser requests mic permission, captures audio
- User speaks, Nova Sonic responds with voice
- Transcript appears in real-time (`call_transcript` messages)
- User speaks passphrase → `authenticate_user` tool fires → success
- User authorizes recovery → `restart_database` tool fires → demo resolves
- Full cycle: speak → AI responds → tool executes → demo state updates → frontend renders

**Reference patterns:**
- `sample-sonic-cdk-agent/backend/nova_s2s_backend.py` (bidirectional stream + tools via MCP)
- `sample-sonic-sip-server-js/src/ai/nova/NovaProvider.js` (event protocol, tool handling)
- `sample-nova-sonic-websocket-agentcore/frontend/src/App.tsx` (browser audio capture)

---

### Phase 4: Twilio Integration + Voice Mode B

**Goal**: Real phone call via Twilio, audio bridged to Direct Bedrock Nova Sonic.

**Deliverables:**
- [ ] `src_backend/voice/twilio_handler.py` — Outbound call placement via Twilio REST API, TwiML for Media Stream
- [ ] `src_backend/voice/audio_converter.py` — mulaw 8kHz ↔ PCM 24kHz conversion
- [ ] `src_backend/voice/mode_b_direct_twilio.py` — Twilio Media Stream WebSocket ↔ nova_sonic_client bridge
- [ ] Twilio webhook endpoint in FastAPI (receives Media Stream connection)
- [ ] SSM parameter: `demo/oncall_phone_number` seeded with `+44XXXXXXXXXX`
- [ ] Secrets Manager: Twilio credentials (account_sid, auth_token, from_number)
- [ ] CDK: Grant ECS task role access to Twilio secret
- [ ] Frontend: phone number input field, "Call" button shows when Mode A/B selected
- [ ] Frontend: `set_phone_number` message wired to DevPanel

**Success criteria:**
- Select Mode B in UI, click trigger
- Real phone rings at configured number (default `+44XXXXXXXXXX`)
- On answer: AI voice speaks, explains incident
- Spoken passphrase → authenticated
- "Restart the database" → tool fires, demo resolves
- Call ends gracefully
- Transcript appears in frontend throughout

**Reference patterns:**
- `sample-amazon-nova-sonic-twilio-integration/src/server.ts` (Twilio outbound + Media Stream)
- `sample-sonic-sip-server-js/src/audio/audioTools.js` (mulaw ↔ PCM conversion)

---

### Phase 5: AgentCore + Voice Mode A

**Goal**: Voice agent runs on AgentCore as a BidiAgent, Twilio audio bridges to it.

**Deliverables:**
- [ ] AgentCore agent code (separate directory for container): `src_backend/voice/agentcore_agent/`
  - `agent.py` — BidiAgent with tools
  - `Dockerfile`
  - `requirements.txt`
- [ ] `src_backend/voice/mode_a_agentcore.py` — Twilio audio ↔ AgentCore WebSocket bridge
- [ ] CDK: AgentCore Runtime resource (`CfnRuntime`) with `DockerImageAsset`
- [ ] CDK: IAM roles for AgentCore (Bedrock invoke, DynamoDB read)
- [ ] CDK: Cognito or SigV4 signing for AgentCore WebSocket endpoint
- [ ] Voice router updated to dispatch Mode A

**Success criteria:**
- AgentCore Runtime deploys and shows ACTIVE status
- Mode A selected → Twilio call places → audio routes through AgentCore
- BidiAgent handles conversation + tools identically to Mode B
- Fallback: if AgentCore endpoint unhealthy, UI shows warning, user can switch to Mode B

**Reference patterns:**
- `sample-Nova-Sonic-AgentCore-Healthcare-Call-Center/backend/agent.py` (BidiAgent setup)
- `sample-Nova-Sonic-AgentCore-Healthcare-Call-Center/infrastructure/` (CfnRuntime CDK)
- `sample-nova-sonic-websocket-agentcore/cdk/lib/runtime-stack.ts` (AgentCore CDK in TS)

---

### Phase 6: Master Agent Orchestration + Polish

**Goal**: Full SoP-driven flow where Master Agent orchestrates the entire incident lifecycle.

**Deliverables:**
- [ ] `src_backend/agents/master_agent.py` — Strands Agent with tools: `assess_severity`, `activate_diagnosis`, `activate_voice_call`, `update_incident_status`
- [ ] `src_config/prompts/master_agent_prompt.json` — SoP-following orchestration prompt
- [ ] `src_config/prompts/master_agent_soul.json` — Master agent personality
- [ ] Integration: Demo controller triggers Master Agent (not individual sub-agents directly)
- [ ] Master Agent decides: severity → diagnosis → escalation route
- [ ] End-to-end timing: full cycle completes within 2-3 minutes
- [ ] Error handling: if any agent/call fails, demo gracefully resets after timeout
- [ ] Frontend: agent activity indicators (which agent is active)

**Success criteria:**
- Incident triggers Master Agent
- Master calls Diagnosis Agent → receives RCA
- Master evaluates severity (always CRITICAL for demo) → routes to voice
- Voice call completes → Master confirms resolution → updates state
- Full demo loop: HEALTHY → detect (3s) → diagnose (10-15s) → call (60-90s) → recover (5s) → HEALTHY
- Auto-loop repeats cleanly without state leaks
- Manual reset works at any point in the cycle

**Reference patterns:**
- `CLAUDE.md` Agent Framework Pattern
- `src-ai-recruiter-platform-01` (multi-agent orchestration with Strands)

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

- [ ] **Phase 1**: Local Docker run + WebSocket client (wscat) → verify state transitions
- [ ] **Phase 2**: Trigger incident → verify metrics spike + RCA output in logs
- [ ] **Phase 3**: Browser mic test → verify Nova Sonic responds + tools execute
- [ ] **Phase 4**: Real phone call → verify audio quality + tool execution
- [ ] **Phase 5**: AgentCore deployment → verify identical behavior to Mode B
- [ ] **Phase 6**: Full loop timing → verify < 3 minutes end-to-end
- [ ] **Regression**: Reset at any phase → verify clean return to HEALTHY
