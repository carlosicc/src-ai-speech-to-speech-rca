# Frontend API Contract

## WebSocket Messages (ws://backend/ws)

### Server → Client

```json
{"type": "system_status", "payload": {"systems": [{"name": "db-prod-01", "status": "healthy"}]}, "timestamp": "..."}
{"type": "incident_detected", "payload": {"incident_id": "...", "severity": "critical", "service": "db-prod-01"}, "timestamp": "..."}
{"type": "phase_update", "payload": {"incident_id": "...", "phase": "diagnosing", "agent": "diagnosis", "details": "..."}, "timestamp": "..."}
{"type": "call_started", "payload": {"incident_id": "...", "phone_number": "+39..."}, "timestamp": "..."}
{"type": "call_transcript", "payload": {"speaker": "agent|human", "text": "..."}, "timestamp": "..."}
{"type": "incident_resolved", "payload": {"incident_id": "...", "resolution": "..."}, "timestamp": "..."}
```

### Client → Server

```json
{"type": "trigger_incident", "payload": {}}
{"type": "reset_demo", "payload": {}}
{"type": "set_phone_number", "payload": {"phone_number": "+39..."}}
```

## REST API (future)

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/status | Current system status |
| GET | /api/v1/incidents | List incidents |
| POST | /api/v1/incidents/trigger | Manually trigger incident |
| POST | /api/v1/demo/reset | Reset demo to steady state |
