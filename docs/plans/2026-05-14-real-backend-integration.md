# Plan: Real Backend Integration — RDS + CloudWatch + Live Agent Tools

**Goal**: Replace the mocked aurora-db simulation with a real RDS Aurora MySQL instance, real CloudWatch metrics, and real agent tools that query AWS APIs. The phone call (already working via Twilio Mode B) triggers from a real incident. Other 6 services in the UI remain mocked.

**Constraint**: This is a 3-minute booth demo. Prioritize reliability, fast recovery, and visual impact. The "break" must be reversible in <30 seconds.

---

## Phase 1 — RDS Aurora MySQL Instance (CDK) ✅ COMPLETED (2026-05-14)

**What**: Provision a small Aurora MySQL cluster that the demo can "break" and "fix."

**Implementation** (added to `RcaBackendStack-dev01`, not a separate stack):
- Aurora MySQL Serverless v2 (0.5–1 ACU) in existing VPC private subnets
- Cluster identifier: `rca-rds-aurora-cluster-dev01`
- Instance identifier: `rca-rds-aurora-writer-dev01`
- Engine: Aurora MySQL 3.08.0 (MySQL 8.0 compatible)
- Default database: `operations`
- Security group `rca-backend-sg-rds-dev01`: inbound 3306 from ECS SG only, no outbound
- Master credentials auto-generated in Secrets Manager: `rca-secret-rds-admin-000000000000-eu-west-1-dev01`
- ECS task role granted: `rds:DescribeDBClusters`, `rds:DescribeDBInstances`, `rds:StopDBCluster`, `rds:StartDBCluster`
- ECS container env vars: `RDS_CLUSTER_ENDPOINT`, `RDS_SECRET_ARN`
- CDK outputs: `RdsClusterEndpoint`, `RdsSecretArn`
- `pymysql>=1.1.0` added to `src_backend/requirements.txt`
- Seed script bundled in Docker image at `scripts/seed_rds.py`
- Database seeded with 1000 rows in `demo_transactions` table

**Key Resources (deployed)**:
| Resource | Value |
|----------|-------|
| Cluster endpoint | `rca-rds-aurora-cluster-dev01.cluster-cehs8psrpx2f.eu-west-1.rds.amazonaws.com` |
| Secret ARN | `arn:aws:secretsmanager:eu-west-1:000000000000:secret:rca-secret-rds-admin-000000000000-eu-west-1-dev01-XXXXXX` |
| VPC | `vpc-0ec863f18ae1127e4` |
| ECS SG | `sg-YYYYYYYYYYYYYYYYY` |
| Private subnets | `subnet-07677c87ba9e876a9`, `subnet-0d29a6350ab0afe24` |

**Re-seed command** (runs as one-shot ECS task):
```bash
aws ecs run-task \
  --cluster rca-backend-ecs-cluster-dev01 \
  --task-definition rca-backend-task-dev01 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-07677c87ba9e876a9,subnet-0d29a6350ab0afe24],securityGroups=[sg-YYYYYYYYYYYYYYYYY],assignPublicIp=DISABLED}" \
  --overrides '{"containerOverrides":[{"name":"rca-backend-agent","command":["python","scripts/seed_rds.py"]}]}' \
  --region eu-west-1
```

**Files changed**:
- `src_infra/stack_backend.py` — Aurora cluster, SG, IAM, env vars, CDK outputs
- `src_backend/requirements.txt` — added `pymysql>=1.1.0`
- `src_backend/scripts/seed_rds.py` — seed script (bundled in Docker image)
- `src_config/scripts/seed_rds.py` — standalone seed script (runs with AWS creds + VPC access)

---

## Phase 2 — Real CloudWatch Metrics for aurora-db ✅ COMPLETED (2026-05-14)

**What**: Replace the `MonitoringSimulator` synthetic metrics for `aurora-db` with real CloudWatch `GetMetricStatistics` calls. Other 6 services stay synthetic.

**Implementation**:
- New module `src_backend/metrics/cloudwatch_rds.py`:
  - `CloudWatchRdsMetrics` class — background async poller (every 10s)
  - Fetches: `CPUUtilization`, `FreeableMemory`, `ReadIOPS`, `WriteIOPS`, `DatabaseConnections`
  - Converts `FreeableMemory` (bytes) → percentage used (based on 1GB for 0.5 ACU)
  - Combines `ReadIOPS + WriteIOPS` into single `iops` value
  - Returns `{"cpu": int, "mem": int, "iops": int}` — same shape frontend expects
  - Graceful fallback: returns `None` if not yet ready → falls back to synthetic
- Modified `MonitoringSimulator._loop()`:
  - For `aurora-db` when **not in incident**: uses `cloudwatch_rds.get_current_metrics()`
  - For `aurora-db` during **incident**: still uses synthetic spike values (CPU 95-100%, IOPS 0)
  - For all other 6 services: unchanged synthetic generation
- IAM: `cloudwatch:GetMetricStatistics`, `cloudwatch:GetMetricData` on `*` added to ECS task role
- New package `src_backend/metrics/__init__.py`

**Verified (live)**:
- DB running → WebSocket emits: `{"service": "aurora-db", "cpu": 46, "mem": 25, "iops": 3}` (real idle values)
- No errors in ECS logs; poller starts cleanly
- ECS service deployed and stable (1/1 running, rollout COMPLETED)
- All 162 tests pass (6 new: `test_cloudwatch_rds.py` + 1 CDK assertion)

**Files changed**:
- `src_backend/metrics/__init__.py` — new package
- `src_backend/metrics/cloudwatch_rds.py` — CloudWatch poller module
- `src_backend/monitoring_simulator.py` — import + start/stop poller + use real metrics in loop
- `src_infra/stack_backend.py` — CloudWatch IAM permissions on task role
- `tests/unit/test_cloudwatch_rds.py` — 6 unit tests
- `tests/unit/test_backend_stack.py` — 1 new CDK assertion for CloudWatch permissions

---

## Phase 3 — Real Agent Tools (Diagnosis Agent) ✅ COMPLETED (2026-05-14)

**What**: Replace simulated tool responses with real AWS API calls. The diagnosis agent will query actual CloudWatch Logs, RDS status, and metrics.

**Implementation**:
- `pull_logs` tool: Queries CloudWatch Logs Insights on `/aws/rds/cluster/rca-rds-aurora-cluster-dev01/error`
  - Last N minutes, filters ERROR/WARNING, returns real log lines or "no errors found"
  - Falls back to simulated response on any AWS failure
- `check_health` tool: Calls `rds:DescribeDBClusters` + `cloudwatch:GetMetricStatistics`
  - Returns real status (available/stopped), CPU%, memory%, connections
  - Falls back to simulated "UNHEALTHY" response on any AWS failure
- `check_recent_changes` tool: Calls `rds:DescribeEvents` (last 24h)
  - Returns real RDS events (start/stop/failover) or "no recent changes"
  - Falls back to simulated ETL scenario on any AWS failure
- IAM: `logs:StartQuery`, `logs:GetQueryResults` (scoped to RDS log group), `rds:DescribeEvents` (wildcard)
- New env var: `RDS_CLUSTER_ID` passed to container
- Non-aurora services still use simulated responses (unchanged)

**Verified (live)**:
- DB running → `check_health` returns: "Status: AVAILABLE, CPU: 45%, Memory: 25%, Connections: 0"
- `check_recent_changes` returns real RDS events (e.g., "DB cluster created")
- Service deployed and stable (1/1 running, rollout COMPLETED, no errors in logs)
- All 176 tests pass (14 new: `test_diagnosis_tools.py` covering real + fallback paths)

**Files changed**:
- `src_backend/agents/diagnosis_agent.py` — real AWS API calls with fallback
- `src_infra/stack_backend.py` — IAM permissions + RDS_CLUSTER_ID env var
- `tests/unit/test_diagnosis_tools.py` — 14 new tests (real API paths + fallback + CDK assertions)
- `tests/unit/test_phase2.py` — updated 3 tests to mock real calls (test fallback behavior)

---

## Phase 4 — The "Break" Mechanism

**What**: A controlled way to make the RDS cluster go down, detectable by the agents and visible in the UI.

**Options** (pick one):
1. **Stop Cluster** (`rds:StopDBCluster`) — takes ~30s, real CloudWatch alarm fires, reversible via `StartDBCluster` (~60s). Most realistic.
2. **Kill connections + overload** — run a stored procedure that saturates connections. Faster to trigger (~5s) but harder to detect cleanly.
3. **Failover** (`rds:FailoverDBCluster`) — triggers automatic failover, ~15s downtime, self-recovers. No manual "fix" needed.

**Recommended**: Option 1 (Stop Cluster) for the demo because:
- Visually dramatic (status goes to "stopped", all metrics drop to 0)
- Easy to trigger from DevPanel: new button "Break DB"
- Easy to fix: `StartDBCluster` or agent's `restart_database` tool calls it
- ~30s to break, ~60s to recover — fits the 3-minute loop

**Deliverables**:
- New DevPanel button: "Break DB" → sends `{ type: "break_database", payload: {} }`
- Backend handler: calls `rds:StopDBCluster`
- Modify `restart_database` voice tool: calls `rds:StartDBCluster` (currently just updates demo state)
- CloudWatch Alarm (CDK): `StatusCheckFailed` or `CPUUtilization < 1% for 1 minute` → fires SNS
- Optional: SNS → Lambda → triggers `trigger_incident` via HTTP to the backend (auto-detection)

**Recovery flow**:
1. Presenter clicks "Break DB" (or auto-detection fires)
2. Metrics drop to 0 in UI within ~30s
3. Master agent activates, diagnosis agent sees `status=stopped`
4. Voice call placed to DBA
5. DBA says "restart database" → voice tool calls `StartDBCluster`
6. Cluster comes back (~60s), metrics resume, UI shows HEALTHY

**Verification**:
- Full end-to-end: Break → Detect → Diagnose → Call → Fix → Recover
- Total loop time: ~3 minutes (matches demo cadence)

---

## Phase 5 — CloudWatch Alarm Auto-Detection (Optional)

**What**: Instead of clicking "Break DB" manually, let CloudWatch detect the failure and trigger the incident automatically.

**Deliverables**:
- CloudWatch Alarm (CDK): `aurora-db CPUUtilization = 0 for 1 datapoint`
- SNS Topic → Lambda (tiny function, <20 lines)
- Lambda calls backend `/api/trigger-incident` endpoint (new, token-protected)
- Backend exposes `POST /api/trigger-incident` → calls `demo_controller.trigger_incident()`

**Why optional**: For a booth demo, manual "Break DB" button is more reliable and lets the presenter control timing. Auto-detection adds realism but also adds lag (~60s for alarm to fire).

**Verification**:
- Stop cluster manually via AWS Console
- Within 90s, alarm fires → Lambda triggers → incident begins on UI automatically

---

## Phase 6 — Polish & Demo Hardening

**What**: Make the full real flow reliable for repeated demos.

**Deliverables**:
- **Fast reset**: Reset button also calls `StartDBCluster` if cluster is stopped
- **Pre-check**: On app startup, verify RDS cluster is `available` — log warning if not
- **Cost control**: Auto-stop cluster after 30 min of inactivity (EventBridge rule)
- **Demo script**: Step-by-step guide for presenter in `docs/demo-script.md`
- **Timeout tuning**: Adjust phase durations for real AWS latency (~30s stop, ~60s start)
- **Error display**: If agent tool gets a real AWS error, show it in the log panel (educational for audience)

**Verification**:
- Run 5 consecutive demo loops without manual intervention between them
- Each loop: healthy → break → detect → diagnose → call → fix → recover → healthy

---

## Architecture After All Phases

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (CloudFront + S3)                             │
│  - Metrics Panel: real RDS metrics + 6 mocked services  │
│  - Agent Logs: real LLM output from Strands agents      │
│  - DevPanel: Break DB / Reset / Auto toggle             │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket (wss://)
┌────────────────────▼────────────────────────────────────┐
│  ECS Fargate (FastAPI + WebSocket)                       │
│                                                          │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ Master Agent │→ │ Diag Agent  │→ │ Voice Agent   │  │
│  │ (Strands)    │  │ (Strands)   │  │ (Nova Sonic)  │  │
│  └──────────────┘  └──────┬──────┘  └───────┬───────┘  │
│                            │                  │          │
│  Real AWS Tools:           │     Twilio Call: │          │
│  - rds:Describe*           │     - Mode B    │          │
│  - cloudwatch:GetMetric*   │                  │          │
│  - logs:StartQuery         │                  │          │
│  - rds:StartDBCluster      │                  │          │
└────────────────────────────┼──────────────────┼──────────┘
                             │                  │
              ┌──────────────▼───┐    ┌─────────▼─────────┐
              │  Aurora MySQL    │    │  Twilio + Phone    │
              │  (Serverless v2) │    │  (real call)       │
              │  0.5-1 ACU       │    └───────────────────┘
              └──────────────────┘
                       │
              ┌────────▼─────────┐
              │  CloudWatch      │
              │  Metrics + Logs  │
              │  + Alarms        │
              └──────────────────┘
```

---

## Cost Estimate (dev01, eu-west-1)

| Resource | Monthly Cost |
|----------|-------------|
| Aurora Serverless v2 (0.5 ACU, ~2h/day active) | ~$5-10 |
| CloudWatch metrics/alarms | ~$1 |
| NAT Gateway (already exists) | $0 incremental |
| ECS Fargate (already exists) | $0 incremental |
| **Total incremental** | **~$6-11/month** |

---

## Execution Order & Dependencies

```
Phase 1 (RDS) ✅ ──→ Phase 2 (Metrics) ✅ ──→ Phase 3 (Agent Tools) ✅
                                                       │
                                            Phase 4 (Break) ──→ Phase 5 (Auto-Detect)
                                                       │
                                            Phase 6 (Polish)
```

Phases 1→2→3→4 are sequential (each depends on the prior).  
Phase 5 is optional and independent of Phase 6.  
Phase 6 can start after Phase 4.

**Current status**: Phases 1–3 complete. Phase 4 is next — implement the "Break DB" mechanism (StopDBCluster button + real recovery via StartDBCluster).

---

## What Stays Mocked

| Service | Why |
|---------|-----|
| ecs-cluster | No real incident to simulate — ECS is hosting our app |
| lambda | No Lambda in current arch (deprecated) |
| api-gateway | No API GW in current arch |
| s3-storage | S3 doesn't "go down" in a demo-friendly way |
| monitoring | Meta — it IS the monitoring |
| network | VPC/networking doesn't degrade visibly |

Only `aurora-db` goes real. The mocked services still show "cascading failures" when the DB is down (visually compelling, educational).
