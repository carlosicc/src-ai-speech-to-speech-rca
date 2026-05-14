# Frontend API Contract

## WebSocket Messages (wss://backend/ws)

### Server → Client

```json
{"type": "system_status", "payload": {"systems": [{"name": "aurora-db", "status": "healthy"}], "phase": "HEALTHY", "voice_mode": "mode_c", "auto_advance": true, "active_agent": null}, "timestamp": "..."}
{"type": "incident_detected", "payload": {"incident_id": "uuid", "severity": "critical", "service": "aurora-db"}, "timestamp": "..."}
{"type": "phase_update", "payload": {"phase": "DIAGNOSING", "agent": "diagnosis", "details": "...", "incident_id": "uuid"}, "timestamp": "..."}
{"type": "agent_activity", "payload": {"agent": "master|diagnosis|voice", "status": "active|assessing|running|calling|complete|error"}, "timestamp": "..."}
{"type": "agent_log", "payload": {"message": "...", "level": "info|warn|error|success"}, "timestamp": "..."}
{"type": "call_started", "payload": {"incident_id": "uuid", "phone_number": "+44...", "voice_mode": "mode_a|mode_b|mode_c"}, "timestamp": "..."}
{"type": "call_transcript", "payload": {"speaker": "agent|human", "text": "..."}, "timestamp": "..."}
{"type": "audio_output", "payload": {"audio": "<base64_pcm_24khz>"}, "timestamp": "..."}
{"type": "metrics_update", "payload": {"service": "aurora-db", "cpu": 85, "mem": 72, "iops": 3200}, "timestamp": "..."}
{"type": "incident_resolved", "payload": {"incident_id": "uuid", "resolution": "..."}, "timestamp": "..."}
```

### Client → Server

```json
{"type": "trigger_incident", "payload": {"service": "aurora-db"}}
{"type": "reset_demo", "payload": {}}
{"type": "set_phone_number", "payload": {"phone_number": "+44XXXXXXXXXX"}}
{"type": "set_voice_mode", "payload": {"mode": "mode_a|mode_b|mode_c"}}
{"type": "set_auto_advance", "payload": {"enabled": true, "interval_seconds": 180}}
{"type": "audio_input", "payload": {"audio": "<base64_pcm_16khz>"}}
{"type": "stop_voice", "payload": {}}
```

## Phase State Machine

```
HEALTHY → INCIDENT_DETECTED → DIAGNOSING → CALLING → RECOVERING → RESOLVED → HEALTHY
```

## Agent Activity Flow

During the DIAGNOSING phase, the Master Agent orchestrates:

```
master:active → master:assessing → diagnosis:running → diagnosis:complete → voice:calling
```

The frontend shows agent roster chips that highlight the currently active agent.

## REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (returns `{"status": "ok"}`) |
| GET/POST | `/twilio/outbound-call` | TwiML webhook for Twilio outbound calls |
| WebSocket | `/twilio/media-stream` | Twilio Media Stream audio bridge |
| GET | `/{path}` | Frontend static files (same-origin) |
