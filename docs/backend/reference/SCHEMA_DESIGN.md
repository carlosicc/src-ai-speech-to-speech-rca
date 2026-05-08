# DynamoDB Schema Design

**Table**: `rca-ddb-table-app-{env}`  
**Billing**: Pay-per-request  
**PITR**: Enabled (7 days)  
**TTL**: `expires_at` attribute

---

## Entity Key Patterns

| Entity | PK | SK | Key Attributes |
|--------|----|----|---------------|
| Incident | `INCIDENT#{id}` | `METADATA` | status, severity, service_name, started_at, resolved_at, rca_summary |
| Incident Phase | `INCIDENT#{id}` | `PHASE#{timestamp}` | phase_name, agent_name, details, success |
| Prompt | `PROMPT#{agent_type}` | `LATEST` | prompt_text, max_tokens, version |
| Prompt Version | `PROMPT#{agent_type}` | `v{n}` | prompt_text, max_tokens |
| Soul | `SOUL#{agent_name}` | `LATEST` | identity, personality, values, boundaries |
| Config | `CONFIG#{name}` | `LATEST` | value |
| Demo State | `DEMO#state` | `CURRENT` | phase, started_at, incident_id |

---

## Access Patterns

| Pattern | Key Condition | Use Case |
|---------|--------------|----------|
| Get incident | PK=`INCIDENT#{id}`, SK=`METADATA` | Load incident details |
| List phases | PK=`INCIDENT#{id}`, SK begins_with `PHASE#` | Timeline of incident |
| Get prompt | PK=`PROMPT#{type}`, SK=`LATEST` | Load agent prompt |
| Get soul | PK=`SOUL#{name}`, SK=`LATEST` | Load agent personality |
| Get demo state | PK=`DEMO#state`, SK=`CURRENT` | Frontend state sync |

---

## Notes

- All timestamps in ISO 8601 format (UTC)
- Incident IDs are ULIDs (sortable, unique)
- Demo state is overwritten on each loop reset
