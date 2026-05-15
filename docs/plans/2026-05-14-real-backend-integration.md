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

## Phase 4 — The "Break" Mechanism ✅ COMPLETED (2026-05-14)

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

**Implementation (Option 1 — Stop Cluster)**:
- New module `src_backend/shared/rds_operations.py`: `stop_db_cluster()`, `start_db_cluster()`, `get_cluster_status()`
- WebSocket handler: `break_database` message → calls `stop_db_cluster()` → triggers incident via demo_controller
- Voice tool `restart_database`: now calls `start_db_cluster()` (real AWS) + advances phase to RECOVERING
- Reset handler: also calls `start_db_cluster()` to ensure cluster recovers on demo reset
- DevPanel: new "Break DB" button (AWS OPERATIONS section), disabled when not HEALTHY
- Config: `RDS_CLUSTER_ID` and `RDS_REGION` added to `shared/config.py`
- Tests: 18 new tests in `tests/unit/test_break_mechanism.py` (all passing)

**Verified (live)**:
- ECS service deployed and stable (1/1 running, rollout COMPLETED)
- RDS cluster status: `available`
- All 194 tests pass
- Frontend builds and deploys cleanly (new "Break DB" button visible in DevPanel)

**Files changed**:
- `src_backend/shared/config.py` — added `RDS_CLUSTER_ID`, `RDS_REGION`
- `src_backend/shared/rds_operations.py` — new module (stop/start/status)
- `src_backend/websocket_server.py` — `break_database` handler + reset calls `start_db_cluster`
- `src_backend/voice/voice_tools.py` — `_restart_database` now calls real `start_db_cluster()`
- `src_frontend/app/src/components/DevPanel.tsx` — "Break DB" button in AWS OPERATIONS section
- `tests/unit/test_break_mechanism.py` — 18 new tests

---

## Phase 4.1 — Replace Stop/Start with Security Group "Break" (Supersedes Phase 4) ✅ COMPLETED (2026-05-14)

**Why**: `StopDBCluster` takes ~5 minutes to fully stop and ~3 minutes to start. This is unacceptable for a 3-minute demo loop. The audience would be watching a loading spinner.

**New approach**: Remove the inbound MySQL rule from the RDS security group. This:
- Takes effect **instantly** (< 1 second)
- ECS tasks immediately lose connectivity → queries fail → CloudWatch metrics show 0 connections
- Recovery = re-add the security group rule → also instant
- Demo narrative: *"The agent detected a missing port configuration in the firewall, and restored it"*

### How It Works (End-to-End Flow)

```
1. Presenter clicks "Break DB"
   └─→ Backend calls ec2:RevokeSecurityGroupIngress (removes TCP 3306 rule)
   └─→ Backend immediately triggers incident (demo_controller.trigger_incident)

2. Incident flow starts (phases: INCIDENT_DETECTED → DIAGNOSING → CALLING → ...)
   └─→ Diagnosis agent runs tools:
       a) check_network(service="aurora-db")  ← NEW TOOL
          └─→ ec2:DescribeSecurityGroups → detects: "Inbound rule for port 3306 MISSING"
       b) check_health(service="aurora-db")
          └─→ rds:DescribeDBClusters → "Status: AVAILABLE" (DB is fine, just unreachable)
          └─→ cloudwatch:GetMetricStatistics → "Connections: 0"
       c) pull_logs(service="aurora-db")
          └─→ May show connection timeout errors
   └─→ Agent produces RCA: "Security group misconfiguration — port 3306 blocked"

3. Voice call placed to DBA (Twilio Mode B)
   └─→ Voice agent explains: "The database security group is missing port 3306 inbound rule.
        I need your authorization to restore the firewall configuration."
   └─→ DBA authenticates + says "restore the firewall" (or "fix it", "yes", etc.)

4. Voice tool `restore_connectivity` triggered
   └─→ ec2:AuthorizeSecurityGroupIngress (re-adds TCP 3306 rule) — INSTANT
   └─→ Demo phase advances to RECOVERING → RESOLVED → HEALTHY
   └─→ Metrics resume within next CloudWatch poll (~10s)
```

### Key Design Decisions

| Question | Answer |
|----------|--------|
| What polls the DB? | **Backend** (`CloudWatchRdsMetrics` in `metrics/cloudwatch_rds.py`) polls CloudWatch every 10s. This runs server-side — does NOT require UI to be open. |
| Does the UI need to be open to detect? | **No** — but in current design we don't auto-detect. The "Break DB" button both breaks AND triggers the incident immediately. Metrics are pushed over WebSocket. |
| Which tools diagnose the issue? | **`check_network`** (new) + `check_health` + `pull_logs`. The new tool calls `ec2:DescribeSecurityGroups` to detect the missing rule. |
| Do prompts need updating? | **Yes** — both diagnosis agent prompt (add "check network connectivity") and voice agent prompt (say "firewall rule" not "restart database"). |

### Security Group Details

| Resource | Value |
|----------|-------|
| RDS SG | `sg-XXXXXXXXXXXXXXXXX` (`rca-backend-sg-rds-dev01`) |
| ECS SG (source) | `sg-YYYYYYYYYYYYYYYYY` |
| Inbound rule | TCP 3306 from ECS SG, description: "MySQL from ECS tasks" |
| VPC | `vpc-0ec863f18ae1127e4` |

### Deliverables

1. **Refactor `src_backend/shared/rds_operations.py`** → rename to `src_backend/shared/network_operations.py`:
   - `revoke_db_access()`: calls `ec2:RevokeSecurityGroupIngress` to remove the 3306 rule
   - `restore_db_access()`: calls `ec2:AuthorizeSecurityGroupIngress` to re-add the 3306 rule
   - `check_sg_rule_exists()`: calls `ec2:DescribeSecurityGroups` → returns bool (is rule present?)
   - Remove old `stop_db_cluster()` / `start_db_cluster()` functions

2. **New diagnosis tool `check_network`** in `src_backend/agents/diagnosis_agent.py`:
   - Calls `ec2:DescribeSecurityGroups` for the RDS SG
   - Reports whether port 3306 inbound rule from ECS SG exists
   - Returns clear message: "ALERT: Port 3306 inbound rule MISSING from security group" or "Network: OK, port 3306 rule present"

3. **Update WebSocket `break_database` handler** in `websocket_server.py`:
   - Calls `revoke_db_access()` instead of `stop_db_cluster()`
   - Still triggers incident immediately via `demo_controller.trigger_incident("aurora-db")`

4. **Rename voice tool `restart_database` → `restore_connectivity`** in `voice/voice_tools.py`:
   - Calls `restore_db_access()` (re-adds SG rule) instead of `start_db_cluster()`
   - Update tool description: "Restore network connectivity by re-adding the firewall rule"
   - Update TOOL_SPECS name and description accordingly

5. **Update `reset_demo` handler**:
   - Calls `restore_db_access()` to ensure rule is always present after reset

6. **CDK IAM changes** in `src_infra/stack_backend.py`:
   - Add to ECS task role: `ec2:RevokeSecurityGroupIngress`, `ec2:AuthorizeSecurityGroupIngress`, `ec2:DescribeSecurityGroups`
   - Scope to the RDS SG ARN: `arn:aws:ec2:eu-west-1:000000000000:security-group/sg-XXXXXXXXXXXXXXXXX`
   - Pass new env vars to container: `RDS_SECURITY_GROUP_ID`, `ECS_SECURITY_GROUP_ID`

7. **Update agent prompts** (DynamoDB seeds in `src_config/prompts/`):
   - **Diagnosis agent**: Add "4. Check network connectivity and security group configuration" to investigation steps
   - **Voice agent**: Change narrative from "restart database" to "restore the firewall configuration on port 3306"

8. **Config additions** in `src_backend/shared/config.py`:
   - `RDS_SECURITY_GROUP_ID` = `sg-XXXXXXXXXXXXXXXXX`
   - `ECS_SECURITY_GROUP_ID` = `sg-YYYYYYYYYYYYYYYYY`
   - Remove (or keep as fallback): `RDS_CLUSTER_ID`, `RDS_REGION`

9. **Update tests** in `tests/unit/test_break_mechanism.py`:
   - Replace stop/start mocks with revoke/authorize mocks
   - Add tests for `check_network` tool
   - Test SG rule detection (present/missing)
   - Test voice tool calls `restore_db_access()`

10. **Deploy and verify**: `cdk deploy --all --require-approval never`, run pytest, confirm instant cycle

### Config (env vars needed in ECS container)

```
RDS_SECURITY_GROUP_ID=sg-XXXXXXXXXXXXXXXXX
ECS_SECURITY_GROUP_ID=sg-YYYYYYYYYYYYYYYYY
```

### Recovery Flow (Detailed Timing)

| Step | Action | Duration |
|------|--------|----------|
| 1 | Presenter clicks "Break DB" | 0s |
| 2 | `RevokeSecurityGroupIngress` completes | < 1s |
| 3 | Incident triggered, UI shows INCIDENT_DETECTED | < 1s |
| 4 | Phase advances to DIAGNOSING, master agent runs | ~3s |
| 5 | Diagnosis agent calls tools (check_network, check_health, pull_logs) | ~15-30s |
| 6 | RCA produced, phase advances to CALLING | < 1s |
| 7 | Twilio call placed to DBA phone | ~5s ring |
| 8 | Voice conversation (auth + authorization) | ~30-45s |
| 9 | DBA says "fix it" → `restore_db_access()` called | < 1s |
| 10 | Phase advances to RECOVERING → RESOLVED → HEALTHY | ~8s |
| **Total** | | **~90-120s** |

### Verification

- Break: rule removed → `aws ec2 describe-security-groups --group-ids sg-XXXXXXXXXXXXXXXXX` shows empty `IpPermissions`
- Fix: rule re-added → shows TCP 3306 from sg-YYYYYYYYYYYYYYYYY
- Full end-to-end cycle under 2 minutes
- Run 3 consecutive loops with no manual intervention between them

---

## Phase 4.2 — UI Polish (DevPanel Defaults + Toggle Button) ✅ COMPLETED (2026-05-14)

**What**: Three small UI/UX changes to improve the demo presenter experience.

### Deliverables

1. **Auto Advance defaults to OFF**
   - Backend: Change `auto_advance: bool = True` → `False` in `src_backend/shared/state.py`
   - CDK container env: no change needed (state default is authoritative)
   - Frontend: `DevPanel.tsx` — ensure the toggle reflects backend state on connect (already does via `system_status` message)
   - Why: Presenter wants manual control during the demo; auto-advance can be toggled on if desired

2. **Voice Mode defaults to Mode B (Twilio)**
   - Backend: Change `DEFAULT_VOICE_MODE` default from `"mode_c"` to `"mode_b"` in `src_backend/shared/config.py`
   - CDK container env: Change `DEFAULT_VOICE_MODE` from `"mode_c"` to `"mode_b"` in `src_infra/stack_backend.py`
   - Frontend: Change initial `useState("mode_c")` → `useState("mode_b")` in `DevPanel.tsx`
   - Why: The real demo uses a phone call (Mode B); Mode C is only for local testing

3. **DevPanel toggle button visible in the UI**
   - Add a small gear/cog icon button (fixed position, bottom-right corner) that toggles DevPanel visibility
   - Same behaviour as Ctrl+D — just a clickable alternative
   - Use a subtle, semi-transparent style so it doesn't distract from the demo visuals
   - Component: add the button in `DevPanel.tsx` (render it even when `visible=false`)

4. **Fix missing character in S3 Storage room**
   - Bug: `CityScene.ts:119` assigns characters with `const room = i % ROOMS.length` — 6 characters, 7 rooms, so room index 6 (`s3-storage`) never gets one
   - Fix: Add a 7th character to `CHARACTERS` array in `src_frontend/app/src/engine/config.ts`
   - This ensures every room has at least one animated NPC

### Files Changed

| File | Change |
|------|--------|
| `src_backend/shared/state.py` | `auto_advance: bool = False` |
| `src_backend/shared/config.py` | `DEFAULT_VOICE_MODE` default → `"mode_b"` |
| `src_infra/stack_backend.py` | Container env `DEFAULT_VOICE_MODE` → `"mode_b"` |
| `src_frontend/app/src/components/DevPanel.tsx` | Default voice mode `"mode_b"`, gear toggle button (always rendered) |
| `src_frontend/app/src/engine/config.ts` | Added 7th character: `citizen-7`, color `#e59866`, speed `0.35` |
| `src_frontend/app/src/store/sceneStore.ts` | `autoAdvance: false` initial value |
| `src_frontend/app/src/styles/theme.css` | `.dev-panel-toggle` CSS (32px circle, fixed bottom-right, semi-transparent) |
| `tests/unit/test_break_mechanism.py` | Fixture uses `demo_state.voice_mode = "mode_b"` |

### Verified (live)

- Gear button visible bottom-right, clicking toggles DevPanel, Ctrl+D still works
- Voice Mode B highlighted by default in DevPanel
- Auto Advance defaults to OFF on fresh ECS task start
- S3 Storage room has a character walking around
- All 54 tests pass (23 break mechanism + 31 backend/stack)
- Frontend builds clean, both stacks deployed
- ECS 1/1 running, rollout COMPLETED

---

## Phase 6 — Polish & Demo Hardening ✅ COMPLETED (2026-05-14)

**What**: Make the full real flow reliable for repeated demos.

**Deliverables**:
- **Fast reset**: Reset handler calls `restore_db_access()` with confirmation logging ✅
- **Pre-check**: On app startup (`lifespan`), verify SG rule exists — auto-restore if missing ✅
- **Phase timing**: Tuned PHASE_DURATIONS (INCIDENT_DETECTED: 2s, RECOVERING: 3s, RESOLVED: 2s) ✅
- **Error display**: AWS errors from diagnosis tools broadcast to `agent_log` via `_broadcast_aws_error()` ✅
- **Idempotency**: Both revoke and restore handle duplicate errors; integration tests verify double-call ✅
- **Demo script**: `docs/demo-script.md` — presenter guide with pre-checklist, 3-min loop, recovery tips ✅
- **5-loop reliability**: `tests/integration/test_demo_loop.py` — 5 consecutive loops pass in <30s each ✅

**Files changed**:
- `src_backend/main.py` — startup pre-check (SG rule verification + auto-restore)
- `src_backend/demo_controller.py` — tuned PHASE_DURATIONS + wired `set_diagnosis_broadcast`
- `src_backend/websocket_server.py` — enhanced reset log message
- `src_backend/agents/diagnosis_agent.py` — `_broadcast_aws_error()` + `set_diagnosis_broadcast()`
- `src_backend/voice/voice_tools.py` — broadcast error on restore_connectivity failure
- `tests/unit/test_break_mechanism.py` — added `TestIdempotency` class (revoke×2, restore×2)
- `tests/unit/test_phase3.py` — fixed stale `restart_database` tests → `restore_connectivity`
- `tests/integration/test_demo_loop.py` — 5-loop reliability test
- `docs/demo-script.md` — presenter guide

**Verified**:
- All 204 tests pass
- Frontend builds clean
- ECS service deployed and stable

**Verification**:
- Run 5 consecutive demo loops without manual intervention between them
- Each loop: healthy → break → diagnose → call → fix → recover → healthy (under 2 min each)

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
│  - ec2:DescribeSecGroups   │     - Mode B    │          │
│  - ec2:RevokeIngress       │                  │          │
│  - ec2:AuthorizeIngress    │                  │          │
│  - rds:Describe*           │                  │          │
│  - cloudwatch:GetMetric*   │                  │          │
│  - logs:StartQuery         │                  │          │
└────────────────────────────┼──────────────────┼──────────┘
                             │                  │
              ┌──────────────▼───┐    ┌─────────▼─────────┐
              │  Aurora MySQL    │    │  Twilio + Phone    │
              │  (Serverless v2) │    │  (real call)       │
              │  0.5-1 ACU       │    └───────────────────┘
              └──────────────────┘
              ▲                 │
              │ TCP 3306        │
    ┌─────────┴──────────┐     │
    │  Security Group     │     │
    │  (rca-backend-sg-   │     │
    │   rds-dev01)        │     │
    │  ← BREAK: revoke   │     │
    │  ← FIX: authorize  │     │
    └─────────────────────┘     │
                                │
              ┌─────────────────▼─┐
              │  CloudWatch        │
              │  Metrics + Logs    │
              └────────────────────┘
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
                                            Phase 4 (Stop/Start) ✅ [SUPERSEDED]
                                                       │
                                            Phase 4.1 (SG Break) ✅ ──→ Phase 4.2 (UI Polish) ✅ ──→ Phase 6 (Polish)
```

Phases 1→2→3 are sequential (each depends on the prior).  
Phase 4 (stop/start) is superseded by Phase 4.1 (SG break) — faster, more reliable.  
Phase 4.1 (SG break/fix) is deployed and working — instant break/fix cycle.  
Phase 4.2 (UI polish) is deployed — defaults, toggle button, S3 character.  
Phase 5 (auto-detect via CloudWatch alarm) is dropped — not needed since the button triggers the incident immediately.  
Phase 6 (polish) follows after Phase 4.2.

**Current status**: Phases 1–4.2 complete. **Phase 6 (Polish & Demo Hardening) is next** — fast reset with pre-check, idempotent operations, cost control, demo script, error display, and 5-loop reliability testing.

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
