# Reference Implementations

This project uses reference implementations stored in `src_workspaces/references/` for guidance on integration patterns. These are NOT part of the deployed codebase — they serve as architectural references.

---

## Available References

### 1. sample-amazon-nova-sonic-twilio-integration

**Purpose**: Shows how to integrate Twilio voice calls with Amazon Nova Sonic for real-time speech-to-speech conversations.

**Key patterns to reuse**:
- Twilio webhook setup for inbound/outbound calls
- WebSocket bridge between Twilio Media Streams and Nova Sonic
- Audio format conversion (mulaw ↔ PCM)
- Call lifecycle management (connect, stream, hangup)

**Relevant files**: Check the main handler for the Twilio ↔ Nova Sonic WebSocket bridge pattern.

---

### 2. sample-Nova-Sonic-AgentCore-Healthcare-Call-Center

**Purpose**: A healthcare appointment booking agent using Nova Sonic on AgentCore with DynamoDB backend and tool-based architecture.

**Key patterns to reuse**:
- AgentCore runtime configuration for Nova Sonic
- Tool definition pattern (DynamoDB lookups, SNS notifications)
- Conversation flow with tool use during voice calls
- DynamoDB integration for structured data during calls

**Relevant files**: Agent definition, tool implementations, AgentCore deployment config.

---

### 3. sample-nova-sonic-websocket-agentcore

**Purpose**: Complete React + WebSocket voice agent demo with real-time bidirectional conversations, authentication, and one-command deployment.

**Key patterns to reuse**:
- Full-stack WebSocket architecture (React ↔ Backend ↔ Nova Sonic)
- Real-time audio streaming via WebSocket
- Cognito authentication flow
- CDK deployment for the entire stack
- Frontend audio handling (microphone capture, playback)

**Relevant files**: CDK stack, WebSocket handler, React audio components, auth flow.

---

### 4. src-ai-agentic-platforms-guidelines

**Purpose**: Prompt library containing INIT_GUIDELINES.md for scaffolding production-grade serverless projects.

**Key patterns to reuse**:
- Project directory structure conventions
- CLAUDE.md structure and content
- CDK patterns (multi-env, naming, stacks)
- Lambda layer utilities template
- DynamoDB single-table design patterns

**Already applied**: This guideline was used to scaffold the current project.

---

## How to Use References

When implementing a feature, check if a reference covers the integration pattern:

1. **Voice call setup** → `sample-amazon-nova-sonic-twilio-integration`
2. **AgentCore + Nova Sonic** → `sample-Nova-Sonic-AgentCore-Healthcare-Call-Center`
3. **WebSocket streaming** → `sample-nova-sonic-websocket-agentcore`
4. **Project conventions** → `src-ai-agentic-platforms-guidelines`

Read the reference code, adapt the pattern to our naming conventions and architecture — do NOT copy files directly.

## MCP Tools

In addition to references, the following MCP servers are available:
- **AWS Documentation MCP** — search and read AWS docs for service-specific guidance
- **AWS Pricing MCP** — cost estimation for services
- **Bedrock AgentCore MCP** — direct AgentCore API access for runtime management, memory, and identity
