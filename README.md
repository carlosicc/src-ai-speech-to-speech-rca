# From Alert to Action: The AI That Calls You Back

> **AWS Summit Milan 2026 — AI Village Demo**
> An autonomous, multi-agent AI system that detects, diagnoses, and escalates infrastructure incidents in real time.

---

## Overview

Every minute a production system is down, the clock is ticking — on revenue, on customer trust, on your team's sanity. This demo showcases a **fully autonomous AI Operations Center** that compresses the gap between incident detection and resolution from minutes to seconds.

When a database goes silent, a master agent activates specialized sub-agents that pull logs, run health checks, and assess criticality. For non-production systems, the AI sends a WhatsApp alert with a pre-assessed RCA summary. For production systems? **The AI calls you.**

Powered by **Amazon Nova Sonic**, the system places an emergency voice call, walks the on-call engineer through the incident, and — if they authenticate by voice — executes safe recovery commands on the spot.

---

## Demo Narrative

The demo runs as a live loop (~2–3 minutes), designed for booth traffic at the AWS AI Village:

| Phase | What Happens |
|-------|-------------|
| **Steady State** | Dashboard shows a glowing animated city — all systems healthy |
| **Incident** | A production database goes down — building goes dark, characters panic |
| **AI Triage** | Master agent activates, sub-agents diagnose the issue in real-time |
| **Voice Call** | AI calls the on-call DBA via real phone call (Nova Sonic STS) |
| **Authentication** | DBA provides voice passphrase to authorize recovery actions |
| **Resolution** | Agent restarts the database, city recovers, characters celebrate |

Booth visitors can **volunteer to receive the call themselves**, proving the system is live and not pre-recorded.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (The City UI)                         │
│   Animated isometric city + systems panel + live call transcript      │
│   Connects via WebSocket for real-time state updates                 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ WebSocket
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                           BACKEND                                    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Master Agent (Strands Agents SDK on AgentCore)                 │ │
│  │  Orchestrates incident response following SoP                   │ │
│  └───────┬──────────────────┬───────────────────┬──────────────────┘ │
│          │                  │                   │                    │
│  ┌───────▼──────┐  ┌───────▼───────┐  ┌───────▼──────────────────┐   │
│  │  Diagnosis   │  │  Escalation   │  │  Voice Agent             │   │
│  │  Agent       │  │  Agent        │  │  (Amazon Nova Sonic)     │   │
│  │              │  │               │  │                          │   │
│  │  - Pull logs │  │  - WhatsApp   │  │  - Places real call      │   │
│  │  - Health    │  │  - Jira ticket│  │  - Explains incident     │   │
│  │    checks    │  │               │  │  - Authenticates user    │   │
│  │  - RCA       │  │               │  │  - Executes recovery     │   │
│  └──────────────┘  └───────────────┘  └──────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Monitoring Simulator                                            │ │
│  │  Generates synthetic metrics & triggers incidents on demand      │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  WebSocket Server                                                │ │
│  │  Pushes real-time state changes & transcript to frontend         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Voice Modes

The voice agent supports **three redundant modes** for the AI-to-human phone call, giving booth operators flexibility depending on connectivity, reliability needs, and demo impact:

| | Mode A | Mode B | Mode C |
|---|---|---|---|
| **Name** | AgentCore + Twilio | Direct Bedrock + Twilio | Direct Bedrock + Browser |
| **Audio Transport** | Real phone call (Twilio) | Real phone call (Twilio) | Browser microphone & speaker |
| **AI Engine** | AgentCore BidiAgent (managed) | Nova Sonic bidirectional stream | Nova Sonic bidirectional stream |
| **Tool Execution** | Automatic (SDK callbacks) | In-process detection & dispatch | In-process detection & dispatch |
| **External Dependencies** | Bedrock, AgentCore, Twilio | Bedrock, Twilio | Bedrock only |
| **Demo Impact** | Highest — managed agent + real call | High — real phone rings | Medium — no phone, browser-only |
| **Reliability** | Medium — most moving parts | High — fewer hops | Highest — zero external deps |
| **Best For** | Showing AgentCore capabilities | Reliable live phone demo | Fallback / quick iterations |

### Mode A — AgentCore + Twilio

Twilio places an outbound call. Audio streams through Twilio Media Streams into an **AgentCore BidiAgent** running Nova Sonic. The Strands SDK handles the entire bidirectional protocol (session lifecycle, tool specs, barge-in) automatically. You only manage the audio transport bridge.

### Mode B — Direct Bedrock + Twilio

Same real phone call via Twilio, but the backend manages the Nova Sonic bidirectional stream directly using `invoke_model_with_bidirectional_stream`. The backend handles session events, tool detection, and audio resampling (mulaw 8kHz ↔ PCM 24kHz) in-process — fewer moving parts, higher reliability.

#### Call Experience (Modes A & B)

When the phone rings and the callee picks up, they hear **two distinct voices** in sequence:

1. **"Please wait while we connect your call to the AI Operations Center"** — a brief, pre-rendered message from **Amazon Polly** (Matthew, male voice). This plays during the ~2 seconds it takes for the WebSocket Media Stream to connect and Nova Sonic to initialize.

2. **The AI Operations Agent** — powered by **Nova Sonic** (Tiffany, female voice). This is the live, interactive agent that explains the incident, authenticates the caller, and executes recovery tools.

This is a single continuous call — no actual transfer happens. The Polly intro serves as a connection buffer: without it, the callee would hear dead silence while the bidirectional stream establishes. The voice change is intentional — it signals to the callee that they've moved from a static greeting into a live AI conversation.

#### Voice Playback Speed (Mode C)

In browser mode, the AI voice plays back at **1.11x speed** (11% faster than native). This is achieved by creating the browser's AudioContext at 26640 Hz while feeding it 24000 Hz audio — the browser consumes samples faster, resulting in snappier delivery without pitch distortion. The speed factor is configurable in `src_frontend/app/src/lib/audioHandler.ts`.

### Mode C — Direct Bedrock + Browser

No phone call. The browser captures microphone audio (PCM 16kHz), streams it over WebSocket to the backend, which resamples to 24kHz and forwards to Nova Sonic. Responses play back through the browser speaker. Zero external dependencies beyond Bedrock — the most reliable option for demos where Twilio or AgentCore connectivity is uncertain.

### Voice Mode Selector

The frontend DevPanel includes a voice mode dropdown. Operators can switch modes between demo runs. If Mode A or B encounters issues, the system gracefully falls back to Mode C.

---

## Project Structure

```
rca-agent-demo/
├── CLAUDE.md                   ← LLM agent binding rules
├── SOUL.md                     ← Agent personality blueprints
├── app.py                      ← CDK entry point
├── cdk.json                    ← Multi-env configuration
│
├── src_infra/                  ← CDK stacks + Lambda functions
│   ├── stack_infrastructure.py ← DynamoDB, S3, Lambda Layer
│   ├── stack_backend.py        ← ECS Fargate (agents, WebSocket)
│   ├── stack_agentcore.py      ← AgentCore IAM + ECR image
│   ├── stack_frontend.py       ← S3 + CloudFront
│   ├── lambda_functions/       ← Lambda handlers by purpose
│   └── lambda_layers/          ← Shared utilities (rca_utils)
│
├── src_frontend/               ← React/Vite SPA
│   └── app/                    ← Cloudscape Design System UI
│
├── src_config/                 ← Configuration management
│   ├── environments/           ← .env files, SSM parameters
│   ├── scripts/                ← Deployment scripts
│   └── prompts/                ← Agent prompts & souls (JSON)
│
├── docs/                       ← Architecture & planning
│   ├── plans/                  ← Design documents
│   ├── backend/                ← Backend docs, schema design
│   └── frontend/               ← API contracts
│
└── tests/                      ← pytest test suite
```

---

## AWS Services Used

| Service | Role |
|---------|------|
| **Amazon Bedrock AgentCore** | Agent runtime, orchestration |
| **Amazon Nova Sonic** | Speech-to-speech voice agent (real-time call) |
| **Amazon Bedrock** | Foundation model inference (Claude) |
| **Twilio** | Outbound phone call placement |
| **AWS CDK** | Infrastructure as Code |
| **Amazon ECS (Fargate)** | Backend hosting (agents, WebSocket) |
| **Amazon DynamoDB** | Single-table data store (incidents, prompts, config) |
| **Amazon S3** | Log/metric snapshots |

---

## Implementation Status (2026-05-13)

All 6 backend phases are **deployed and operational**:

| Phase | Status | Verified |
|-------|--------|----------|
| 1. WebSocket + Demo Controller | Complete | ECS healthy, 36s cycle |
| 2. Monitoring Simulator + Diagnosis Agent | Complete | Live RCA via Claude Sonnet |
| 3. Voice Mode C (Browser + Bedrock) | Complete | Full voice conversation e2e |
| 4. Voice Mode B (Twilio + Bedrock) | Complete | Real phone call places |
| 5. Voice Mode A (AgentCore) | Complete | Runtime READY, endpoint deployed |
| 6. Master Agent Orchestration | Complete | Full SoP in 41s with LLM |

**Demo loop timing:** 41 seconds (LLM master agent) / 101 seconds (fallback with voice timeout)

---

## Quick Start

```bash
# 1. Activate Python environment
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Deploy infrastructure
npx --package=aws-cdk@latest cdk deploy --all

# 4. Configure secrets (Twilio)
python src_config/scripts/deploy_secrets.py --env dev01

# 5. Access the demo
# Via NLB: https://rca-nlb-ws-pub-dev01-XXXXXXXXXXXXXXXX.elb.eu-west-1.amazonaws.com
# Via CloudFront: https://XXXXXXXXXXXX.cloudfront.net (demo/REDACTED_PASSWORD)

# 6. Local frontend dev
cd src_frontend/app && npm install && npm run dev
```

---

## Context

Built for **AWS Summit Milan 2026** (AI Village booth) by the AWS PACE team. Demonstrates how agentic AI transforms IT operations from reactive to autonomous.
