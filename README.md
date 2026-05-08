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
│                     BACKEND (ECS Fargate)                             │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Master Agent (Strands Agents SDK on AgentCore)                  │ │
│  │  Orchestrates incident response following SoP                    │ │
│  └───────┬──────────────────┬───────────────────┬──────────────────┘ │
│          │                  │                   │                     │
│  ┌───────▼──────┐  ┌───────▼───────┐  ┌───────▼──────────────────┐  │
│  │  Diagnosis   │  │  Escalation   │  │  Voice Agent             │  │
│  │  Agent       │  │  Agent        │  │  (Amazon Nova Sonic)     │  │
│  │              │  │               │  │                          │  │
│  │  - Pull logs │  │  - WhatsApp   │  │  - Places real call      │  │
│  │  - Health    │  │  - Jira ticket│  │  - Explains incident     │  │
│  │    checks    │  │               │  │  - Authenticates user    │  │
│  │  - RCA       │  │               │  │  - Executes recovery     │  │
│  └──────────────┘  └───────────────┘  └──────────────────────────┘  │
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

## Quick Start

```bash
# 1. Activate Python environment
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Deploy infrastructure
cdk deploy --all -c env=dev01

# 4. Configure secrets & parameters
python src_config/scripts/deploy_ssm_parameters.py --env dev01
python src_config/scripts/deploy_secrets.py --env dev01
python src_config/scripts/seed_demo_data.py --env dev01

# 5. Start frontend dev server
cd src_frontend/app && npm install && npm run dev
```

---

## Context

Built for **AWS Summit Milan 2026** (AI Village booth) by the AWS PACE team. Demonstrates how agentic AI transforms IT operations from reactive to autonomous.
