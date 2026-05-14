# Backend Features

## Implemented (All Phases Complete)

- [x] Infrastructure stack (DynamoDB, S3, Lambda Layer)
- [x] ECS Fargate cluster + service (Docker, health checks, circuit breaker)
- [x] WebSocket server (real-time state → frontend, message routing)
- [x] Demo loop controller (auto-loop, manual trigger, reset)
- [x] Monitoring Simulator (synthetic metrics for 7 services, anomaly on incident)
- [x] Diagnosis Agent (Strands SDK — pull logs, health checks, RCA generation)
- [x] Master Agent (Strands SDK — orchestrates full SoP: assess → diagnose → escalate → resolve)
- [x] Voice Mode C (Direct Bedrock + Browser — Nova Sonic bidirectional stream)
- [x] Voice Mode B (Direct Bedrock + Twilio — real phone call)
- [x] Voice Mode A (AgentCore BidiAgent + Twilio — managed runtime)
- [x] Voice tools (authenticate_user, restart_database, check_service_health)
- [x] Twilio integration (outbound call, Media Stream WebSocket, mulaw↔PCM conversion)
- [x] AgentCore Runtime (ARM64 container, BidiAgent, deployed via API)
- [x] Agent activity indicators (agent_activity WebSocket messages → frontend)
- [x] Graceful fallback chain (LLM master → deterministic SoP → force-advance failsafe)
- [x] Prompt/soul loading from DynamoDB with 5-min cache + fallback defaults

## Recently Completed

- [x] Custom domain setup (`rca-demo.aienaws.com` + `ws.rca-demo.aienaws.com`)
- [x] ACM certificates (replaced self-signed cert)
- [x] API token auth on all backend endpoints
- [x] Separate CloudFront (static) and NLB (WebSocket) domains

## Future (P2 — Not for Summit)

- [ ] Escalation Agent (WhatsApp via Twilio)
- [ ] DynamoDB prompt seeding for live prompt editing
- [ ] Barge-in (interruption) handling in voice modes
