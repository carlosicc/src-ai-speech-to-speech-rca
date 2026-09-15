# 3D Data Center UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** Tasks 1–12 implemented on branch `feat/3d-datacenter-ui` (2026-09-14); Task 13 pending manual run
> **Scope:** Add a `/datacenter` route rendering a realistic 3D data-center digital twin of the existing incident demo. The existing UI at `/` stays untouched.

**Goal:** A presenter opens `/datacenter`, sees a cinematic 3D data center with live telemetry, walks (or is flown) to the ECS-to-Aurora service link, holds `E` to disconnect it, and the existing backend runs diagnosis, voice call, remediation and visual recovery, with the cable reconnecting on real backend acknowledgement.

**Architecture:** The backend stays authoritative. It gains one small piece of state (`link_status`) and one new broadcast (`infrastructure_link_update`) wrapped around the existing `revoke_db_access` / `restore_db_access` calls. The frontend adds a lazy-loaded route that reuses every existing Zustand store and the WebSocket client, plus one new shared store (`infrastructureStore`) and one 3D-only UI store. The scene is fully procedural (no GLB assets): instanced rack rows, four labelled hero racks, a tube-geometry cable, an HTML NOC wall. The camera has two modes: **director** (default, phase-driven cinematic shots for booth wow) and **walk** (keyboard first-person with AABB collision for hands-on interaction). No physics engine.

**Tech Stack:** React 18, Vite 5, TypeScript strict, `react-router-dom` v7 (already installed, unused), Zustand 5, `three` + `@react-three/fiber@8` + `@react-three/drei@9` (React-18 line), Vitest, FastAPI backend, pytest.

**What was cut from the v1 draft and why:** Rapier physics (AABB is enough for a room of axis-aligned racks), GLB asset pipeline and licence register (procedural geometry is enough and avoids asset creep), quality presets and adaptive DPR, `webglcontextlost` remount, WebGL end-to-end tests in CI, 4K validation, experience selector and `localStorage` mode persistence (the existing UI keeps `/`, so nothing needs remembering), first-person as the *only* mode (walking for 15 s is slower than the current one-click break, so director mode is the default).

---

## Existing code you will touch (read these first)

| File | What it is |
|---|---|
| `src_backend/shared/state.py` | `DemoState` dataclass, `Phase` enum, global `demo_state` |
| `src_backend/websocket_server.py` | `manager.broadcast`, `build_system_status`, `handle_client_message` (has `break_database` and `reset_demo` handlers) |
| `src_backend/shared/network_operations.py` | `revoke_db_access()`, `restore_db_access()`, `check_sg_rule_exists()` — return `{"status": ..., "message": ...}` |
| `src_backend/voice/voice_tools.py` | `_apply_network_fix()` — the voice agent's remediation tool |
| `src_backend/main.py` | `lifespan()` startup pre-check that restores the SG rule |
| `src_frontend/app/src/app/main.tsx` | Renders `<App />` directly, no router |
| `src_frontend/app/src/lib/websocket.ts` | Singleton socket: `subscribe(handler)`, `send(msg)` |
| `src_frontend/app/src/store/sceneStore.ts` | `state` (phase), `affectedService`, `activeAgent`, `agentStatus`, `connected`, `reset()`, `setAutoAdvance()` |
| `src_frontend/app/src/store/metricsStore.ts` | `metrics[service] = { cpu[], mem[], iops[] }` |
| `src_frontend/app/src/store/agentLogStore.ts` | `entries[]` |
| `src_frontend/app/src/store/voiceStore.ts` | `callActive`, `transcripts[]` |
| `src_frontend/app/src/components/{DevPanel,MetricsPanel,AgentLog}.tsx` | Reused as-is inside the 3D HUD |
| `tests/unit/test_break_mechanism.py` | Existing patterns for mocking `_get_ec2_client` and `demo_controller.trigger_incident` |
| `tests/conftest.py` | Sets `RDS_SECURITY_GROUP_ID` / `ECS_SECURITY_GROUP_ID` env for tests |

Backend service names (used as rack ids so metrics map automatically): `aurora-db`, `ecs-cluster`, `lambda`, `api-gateway`, `s3-storage`, `monitoring`, `network`.

Frontend tests run with `cd src_frontend/app && npm test -- --run`. Backend tests run with `.venv/bin/pytest tests/unit -v` from the repo root.

---

## File structure

**Backend (modify):**
- `src_backend/shared/state.py` — add `LinkStatus` enum and `DemoState.link_status`
- `src_backend/websocket_server.py` — add `LINK_ID`, `build_link_update`, `set_link_status`, `broadcast_link_error`, `sync_link_status_from_aws`; extend `build_system_status`; wrap `break_database` and `reset_demo`
- `src_backend/voice/voice_tools.py` — wrap `_apply_network_fix` with restoring/connected broadcasts
- `src_backend/main.py` — call `sync_link_status_from_aws()` in `lifespan`
- `docs/frontend/api-contract.md` — document the new message and payload field

**Backend (create):**
- `tests/unit/test_infrastructure_link.py`

**Frontend (modify):**
- `src_frontend/app/package.json` — add three/fiber/drei
- `src_frontend/app/vite.config.ts` — vitest `test` block
- `src_frontend/app/src/app/main.tsx` — router with lazy `/datacenter`

**Frontend (create):**
```
src_frontend/app/src/
├── types/infrastructure.ts                 LinkStatus, InfrastructureLink, LinkUpdatePayload
├── store/infrastructureStore.ts            shared link state + requestDisconnect() (+ .test.ts)
└── datacenter/
    ├── DataCenterPage.tsx                  route component: WebGL check, Canvas, HUD, DevPanel
    ├── datacenter.css                      all 3D-view styles (HUD, labels, NOC wall)
    ├── config/layout.ts                    every world coordinate lives here
    ├── lib/collision.ts                    resolveMove() AABB slide (+ .test.ts)
    ├── lib/cameraDirector.ts               shotForPhase() (+ .test.ts)
    ├── lib/holdToConfirm.ts                reduceHold() state machine (+ .test.ts)
    ├── lib/useKeyboard.ts                  held-keys ref hook
    ├── store/dataCenterUiStore.ts          mode, lookingAtLink, hold, panelOpen (+ .test.ts)
    ├── scene/DataCenterScene.tsx           composition
    ├── scene/Facility.tsx                  floor, walls, ceiling, fog, lights, alarm light
    ├── scene/RackRows.tsx                  instanced filler racks + blinking LEDs
    ├── scene/HeroRack.tsx                  labelled rack with status panel + metrics label
    ├── scene/ServiceLink.tsx               ECS→Aurora cable, pulses, split state, raycast target
    ├── scene/NocWall.tsx                   HTML display: phase, agent, event feed, transcript
    ├── scene/CameraRig.tsx                 director/walk camera, keyboard movement, G/V/R keys
    ├── scene/Interaction.tsx               raycast + hold-E + tick
    └── hud/Hud.tsx                         top bar, reticle/prompt, right panel, presenter row
```

---

## Message contract (what Tasks 1–4 build, what Tasks 6+ consume)

Client → server (existing DevPanel keeps sending `{"type":"break_database","payload":{}}`; 3D UI adds fields):

```json
{"type": "break_database", "payload": {"request_id": "<uuid>", "source": "datacenter_3d", "link_id": "ecs-aurora"}}
```

Server → client, new:

```json
{"type": "infrastructure_link_update", "payload": {"link_id": "ecs-aurora", "status": "disconnecting|disconnected|restoring|connected|error", "message": "...", "request_id": "<uuid, only if client sent one>"}, "timestamp": "..."}
```

`system_status.payload` gains one additive field:

```json
"infrastructure_links": [{"id": "ecs-aurora", "source": "ecs-cluster", "target": "aurora-db", "protocol": "tcp", "port": 3306, "status": "connected"}]
```

Sequences:
- Break success: `disconnecting` → `disconnected` → (existing `incident_detected`, `phase_update`…)
- Break AWS failure: `disconnecting` → `error` (backend link_status returns to `connected`; incident not triggered)
- Duplicate break while `disconnecting`: ignored, nothing broadcast
- Reset: `restoring` → `connected` (or `error`, link stays `disconnected`)
- Voice-agent fix: `restoring` → `connected` (or `error`)

Frontend rollback rule on `error`: `disconnecting` → `connected`, `restoring` → `disconnected`, anything else unchanged.

---

## Task 1: Backend link state and message builders

**Files:**
- Modify: `src_backend/shared/state.py`
- Modify: `src_backend/websocket_server.py`
- Create: `tests/unit/test_infrastructure_link.py`

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_infrastructure_link.py`:

```python
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from shared.state import LinkStatus, Phase, demo_state


@pytest.fixture(autouse=True)
def reset_state():
    demo_state.reset()
    demo_state.link_status = LinkStatus.CONNECTED
    yield
    demo_state.reset()
    demo_state.link_status = LinkStatus.CONNECTED


def _link_messages(mock_broadcast) -> list[dict]:
    return [
        c.args[0]["payload"]
        for c in mock_broadcast.call_args_list
        if c.args[0]["type"] == "infrastructure_link_update"
    ]


def _statuses(mock_broadcast) -> list[str]:
    return [p["status"] for p in _link_messages(mock_broadcast)]


class TestLinkState:
    def test_default_link_status_is_connected(self):
        assert demo_state.link_status == LinkStatus.CONNECTED

    def test_system_status_includes_link(self):
        from websocket_server import build_system_status

        demo_state.link_status = LinkStatus.DISCONNECTED
        payload = build_system_status(demo_state)["payload"]
        assert payload["infrastructure_links"] == [{
            "id": "ecs-aurora",
            "source": "ecs-cluster",
            "target": "aurora-db",
            "protocol": "tcp",
            "port": 3306,
            "status": "disconnected",
        }]

    def test_build_link_update_includes_request_id_when_given(self):
        from websocket_server import build_link_update

        msg = build_link_update("disconnecting", request_id="req-1", message="m")
        assert msg["type"] == "infrastructure_link_update"
        assert msg["payload"] == {
            "link_id": "ecs-aurora",
            "status": "disconnecting",
            "message": "m",
            "request_id": "req-1",
        }

    def test_build_link_update_omits_request_id_when_none(self):
        from websocket_server import build_link_update

        msg = build_link_update("connected")
        assert "request_id" not in msg["payload"]
        assert msg["payload"]["message"] == ""

    @pytest.mark.asyncio
    async def test_set_link_status_updates_state_and_broadcasts(self):
        from websocket_server import set_link_status

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc:
            await set_link_status(LinkStatus.RESTORING, request_id=None, message="x")

        assert demo_state.link_status == LinkStatus.RESTORING
        assert _statuses(mock_bc) == ["restoring"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_infrastructure_link.py -v`
Expected: FAIL with `ImportError: cannot import name 'LinkStatus'`

- [x] **Step 3: Add `LinkStatus` and `link_status` to state**

In `src_backend/shared/state.py`, after the `PHASE_ORDER` list add:

```python
class LinkStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    RESTORING = "restoring"
```

In the `DemoState` dataclass add one field after `active_agent`:

```python
    link_status: LinkStatus = LinkStatus.CONNECTED
```

Do **not** touch `reset()`; the WebSocket handler owns link transitions because reset must broadcast `restoring` before AWS is called.

- [x] **Step 4: Add builders to `websocket_server.py`**

Change the import line to:

```python
from shared.state import DemoState, LinkStatus, Phase, demo_state
```

Add `Optional` to the typing import: `from typing import Any, Optional`.

Directly after `manager = ConnectionManager()` add:

```python
LINK_ID = "ecs-aurora"


def build_link_update(status: str, request_id: Optional[str] = None, message: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"link_id": LINK_ID, "status": status, "message": message}
    if request_id:
        payload["request_id"] = request_id
    return {"type": "infrastructure_link_update", "payload": payload}


async def set_link_status(status: LinkStatus, request_id: Optional[str] = None, message: str = "") -> None:
    demo_state.link_status = status
    await manager.broadcast(build_link_update(status.value, request_id, message))


async def broadcast_link_error(message: str, request_id: Optional[str] = None) -> None:
    await manager.broadcast(build_link_update("error", request_id, message))
```

In `build_system_status`, add to the returned `payload` dict after `"active_agent"`:

```python
            "infrastructure_links": [{
                "id": LINK_ID,
                "source": "ecs-cluster",
                "target": "aurora-db",
                "protocol": "tcp",
                "port": 3306,
                "status": state.link_status.value,
            }],
```

- [x] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_infrastructure_link.py tests/unit/test_break_mechanism.py -v`
Expected: all PASS (existing break tests must stay green)

- [x] **Step 6: Commit**

```bash
git add src_backend/shared/state.py src_backend/websocket_server.py tests/unit/test_infrastructure_link.py
git commit -m "feat(backend): add authoritative ECS-Aurora link status and infrastructure_link_update builder"
```

---

## Task 2: Break handler broadcasts link lifecycle and rejects duplicates

**Files:**
- Modify: `src_backend/websocket_server.py` (the `break_database` branch of `handle_client_message`)
- Modify: `tests/unit/test_infrastructure_link.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_infrastructure_link.py`:

```python
class TestBreakDatabaseLinkEvents:
    @pytest.mark.asyncio
    async def test_success_broadcasts_disconnecting_then_disconnected(self):
        from websocket_server import handle_client_message

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock,
                   return_value={"status": "success", "message": "removed"}), \
             patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
            await handle_client_message(json.dumps({
                "type": "break_database",
                "payload": {"request_id": "req-1", "source": "datacenter_3d", "link_id": "ecs-aurora"},
            }))

        assert _statuses(mock_bc) == ["disconnecting", "disconnected"]
        assert all(p["request_id"] == "req-1" for p in _link_messages(mock_bc))
        assert demo_state.link_status == LinkStatus.DISCONNECTED
        mock_trigger.assert_called_once_with("aurora-db")

    @pytest.mark.asyncio
    async def test_already_revoked_counts_as_disconnected(self):
        from websocket_server import handle_client_message

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock,
                   return_value={"status": "already_revoked", "message": "absent"}), \
             patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
            await handle_client_message(json.dumps({"type": "break_database", "payload": {}}))

        assert _statuses(mock_bc) == ["disconnecting", "disconnected"]
        mock_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_aws_error_broadcasts_error_and_rolls_back(self):
        from websocket_server import handle_client_message

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock,
                   return_value={"status": "error", "message": "boom"}), \
             patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
            await handle_client_message(json.dumps({"type": "break_database", "payload": {"request_id": "req-2"}}))

        assert _statuses(mock_bc) == ["disconnecting", "error"]
        assert _link_messages(mock_bc)[-1]["message"] == "boom"
        assert demo_state.link_status == LinkStatus.CONNECTED
        mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_break_while_disconnecting_is_ignored(self):
        from websocket_server import handle_client_message

        demo_state.link_status = LinkStatus.DISCONNECTING
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock) as mock_revoke:
            await handle_client_message(json.dumps({"type": "break_database", "payload": {"request_id": "req-3"}}))

        mock_revoke.assert_not_called()
        assert _statuses(mock_bc) == []

    @pytest.mark.asyncio
    async def test_empty_payload_is_still_accepted(self):
        from websocket_server import handle_client_message

        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.revoke_db_access", new_callable=AsyncMock,
                   return_value={"status": "success", "message": "removed"}), \
             patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock):
            await handle_client_message(json.dumps({"type": "break_database", "payload": {}}))

        assert _statuses(mock_bc) == ["disconnecting", "disconnected"]
        assert all("request_id" not in p for p in _link_messages(mock_bc))
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_infrastructure_link.py::TestBreakDatabaseLinkEvents -v`
Expected: FAIL, `_statuses` returns `[]` (no link messages yet)

- [x] **Step 3: Replace the `break_database` branch**

In `handle_client_message`, replace the whole `if msg_type == "break_database":` block with:

```python
    if msg_type == "break_database":
        request_id = payload.get("request_id")
        if demo_state.phase != Phase.HEALTHY:
            logger.info("break_database ignored: phase is not HEALTHY")
            return
        if demo_state.link_status == LinkStatus.DISCONNECTING:
            logger.warning("break_database ignored: a disconnect is already in progress")
            return
        from shared.network_operations import revoke_db_access
        await set_link_status(LinkStatus.DISCONNECTING, request_id, "Removing ECS -> Aurora TCP/3306 rule")
        result = await revoke_db_access()
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": f"Break DB: {result['message']}", "level": "warn"},
        })
        if result["status"] in ("success", "already_revoked"):
            await set_link_status(LinkStatus.DISCONNECTED, request_id, result["message"])
            from demo_controller import demo_controller
            await demo_controller.trigger_incident("aurora-db")
        else:
            demo_state.link_status = LinkStatus.CONNECTED
            await broadcast_link_error(result["message"], request_id)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_infrastructure_link.py tests/unit/test_break_mechanism.py -v`
Expected: all PASS

- [x] **Step 5: Commit**

```bash
git add src_backend/websocket_server.py tests/unit/test_infrastructure_link.py
git commit -m "feat(backend): broadcast link lifecycle around break_database and reject duplicate requests"
```

---

## Task 3: Reset, voice-agent fix and startup keep link state in sync

**Files:**
- Modify: `src_backend/websocket_server.py` (`reset_demo` branch, new `sync_link_status_from_aws`)
- Modify: `src_backend/voice/voice_tools.py` (`_apply_network_fix`)
- Modify: `src_backend/main.py` (`lifespan`)
- Modify: `tests/unit/test_infrastructure_link.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_infrastructure_link.py`:

```python
class TestRestoreLinkEvents:
    @pytest.mark.asyncio
    async def test_reset_broadcasts_restoring_then_connected(self):
        from websocket_server import handle_client_message

        demo_state.link_status = LinkStatus.DISCONNECTED
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.restore_db_access", new_callable=AsyncMock,
                   return_value={"status": "success", "message": "restored"}), \
             patch("demo_controller.demo_controller.cancel_simulation", new_callable=AsyncMock), \
             patch("voice.voice_router.voice_router.stop_session", new_callable=AsyncMock), \
             patch("websocket_server._cancel_inflight_twilio_call", new_callable=AsyncMock):
            await handle_client_message(json.dumps({"type": "reset_demo", "payload": {}}))

        assert _statuses(mock_bc) == ["restoring", "connected"]
        assert demo_state.link_status == LinkStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_reset_restore_failure_broadcasts_error_and_stays_disconnected(self):
        from websocket_server import handle_client_message

        demo_state.link_status = LinkStatus.DISCONNECTED
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.restore_db_access", new_callable=AsyncMock,
                   return_value={"status": "error", "message": "denied"}), \
             patch("demo_controller.demo_controller.cancel_simulation", new_callable=AsyncMock), \
             patch("voice.voice_router.voice_router.stop_session", new_callable=AsyncMock), \
             patch("websocket_server._cancel_inflight_twilio_call", new_callable=AsyncMock):
            await handle_client_message(json.dumps({"type": "reset_demo", "payload": {}}))

        assert _statuses(mock_bc) == ["restoring", "error"]
        assert demo_state.link_status == LinkStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_voice_fix_broadcasts_restoring_then_connected(self):
        from voice.voice_tools import _apply_network_fix

        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.CALLING
        demo_state.link_status = LinkStatus.DISCONNECTED
        with patch("websocket_server.manager.broadcast", new_callable=AsyncMock) as mock_bc, \
             patch("shared.network_operations.restore_db_access", new_callable=AsyncMock,
                   return_value={"status": "success", "message": "restored"}):
            result = await _apply_network_fix("aurora-db")

        assert result["status"] == "success"
        assert _statuses(mock_bc) == ["restoring", "connected"]
        assert demo_state.phase == Phase.RECOVERING


class TestStartupSync:
    @pytest.mark.asyncio
    async def test_rule_present_sets_connected(self):
        from websocket_server import sync_link_status_from_aws

        demo_state.link_status = LinkStatus.DISCONNECTED
        with patch("shared.network_operations.check_sg_rule_exists", new_callable=AsyncMock, return_value=True), \
             patch("shared.network_operations.restore_db_access", new_callable=AsyncMock) as mock_restore:
            await sync_link_status_from_aws()

        assert demo_state.link_status == LinkStatus.CONNECTED
        mock_restore.assert_not_called()

    @pytest.mark.asyncio
    async def test_rule_missing_and_restore_fails_sets_disconnected(self):
        from websocket_server import sync_link_status_from_aws

        with patch("shared.network_operations.check_sg_rule_exists", new_callable=AsyncMock, return_value=False), \
             patch("shared.network_operations.restore_db_access", new_callable=AsyncMock,
                   return_value={"status": "error", "message": "denied"}):
            await sync_link_status_from_aws()

        assert demo_state.link_status == LinkStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_rule_missing_and_restore_succeeds_sets_connected(self):
        from websocket_server import sync_link_status_from_aws

        demo_state.link_status = LinkStatus.DISCONNECTED
        with patch("shared.network_operations.check_sg_rule_exists", new_callable=AsyncMock, return_value=False), \
             patch("shared.network_operations.restore_db_access", new_callable=AsyncMock,
                   return_value={"status": "success", "message": "restored"}):
            await sync_link_status_from_aws()

        assert demo_state.link_status == LinkStatus.CONNECTED
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_infrastructure_link.py::TestRestoreLinkEvents tests/unit/test_infrastructure_link.py::TestStartupSync -v`
Expected: FAIL (`sync_link_status_from_aws` missing; reset/voice emit no link messages)

- [x] **Step 3: Update the `reset_demo` branch**

In `handle_client_message`, replace from `from shared.network_operations import restore_db_access` through the `else: logger.warning(...)` line inside the `reset_demo` branch with:

```python
        from shared.network_operations import restore_db_access
        await set_link_status(LinkStatus.RESTORING, None, "Restoring ECS -> Aurora TCP/3306 rule")
        restore_result = await restore_db_access()
        if restore_result["status"] in ("success", "already_present"):
            logger.info(f"Reset: SG rule confirmed present (result={restore_result['status']})")
            await set_link_status(LinkStatus.CONNECTED, None, restore_result["message"])
        else:
            logger.warning(f"Reset: SG rule restore returned unexpected status: {restore_result}")
            demo_state.link_status = LinkStatus.DISCONNECTED
            await broadcast_link_error(restore_result["message"])
```

Keep the following `await manager.broadcast(build_system_status(demo_state))` and the reset `agent_log` broadcast as they are.

- [x] **Step 4: Add `sync_link_status_from_aws` to `websocket_server.py`**

After `broadcast_link_error` add:

```python
async def sync_link_status_from_aws() -> None:
    """Startup pre-check: make the real SG rule and demo_state.link_status agree."""
    from shared.network_operations import check_sg_rule_exists, restore_db_access

    if await check_sg_rule_exists():
        demo_state.link_status = LinkStatus.CONNECTED
        logger.info("Startup pre-check: SG rule present — database reachable")
        return
    logger.warning("Startup pre-check: SG rule for port 3306 is MISSING — auto-restoring")
    result = await restore_db_access()
    logger.info(f"Startup pre-check: restore_db_access result={result['status']}")
    if result["status"] in ("success", "already_present"):
        demo_state.link_status = LinkStatus.CONNECTED
    else:
        demo_state.link_status = LinkStatus.DISCONNECTED
```

- [x] **Step 5: Call it from `main.py`**

In `lifespan()`, replace the block from `from shared.network_operations import check_sg_rule_exists, restore_db_access` through the `else: logger.info("Startup pre-check: SG rule present — database reachable")` with:

```python
    from websocket_server import sync_link_status_from_aws

    load_twilio_credentials()
    await sync_link_status_from_aws()
```

(Keep `from shared.config import load_twilio_credentials` above it.)

- [x] **Step 6: Wrap `_apply_network_fix` in `voice_tools.py`**

Replace the body of `_apply_network_fix` up to and including the `if fix_result["status"] == "error":` block with:

```python
async def _apply_network_fix(service: str) -> dict[str, Any]:
    from shared.network_operations import restore_db_access
    from shared.state import LinkStatus
    from websocket_server import broadcast_link_error, set_link_status

    await set_link_status(LinkStatus.RESTORING, None, "DBA authorised recovery — restoring TCP/3306 rule")
    fix_result = await restore_db_access()
    logger.info(f"apply_network_fix result: {fix_result}")

    if fix_result["status"] == "error":
        from agents.diagnosis_agent import _broadcast_aws_error
        _broadcast_aws_error("apply_network_fix", Exception(fix_result["message"]))
        demo_state.link_status = LinkStatus.DISCONNECTED
        await broadcast_link_error(fix_result["message"])
    else:
        await set_link_status(LinkStatus.CONNECTED, None, fix_result["message"])
```

Leave the phase-advance `if demo_state.phase == Phase.CALLING:` block below unchanged.

- [x] **Step 7: Run the whole backend suite**

Run: `.venv/bin/pytest tests/unit -v`
Expected: all PASS

- [x] **Step 8: Commit**

```bash
git add src_backend/websocket_server.py src_backend/voice/voice_tools.py src_backend/main.py tests/unit/test_infrastructure_link.py
git commit -m "feat(backend): sync link status on reset, voice remediation and startup"
```

---

## Task 4: Document the contract

**Files:**
- Modify: `docs/frontend/api-contract.md`

- [x] **Step 1: Add the new server message**

In the `### Server → Client` JSON block, replace the `system_status` line with:

```json
{"type": "system_status", "payload": {"systems": [{"name": "aurora-db", "status": "healthy"}], "phase": "HEALTHY", "voice_mode": "mode_c", "auto_advance": true, "active_agent": null, "infrastructure_links": [{"id": "ecs-aurora", "source": "ecs-cluster", "target": "aurora-db", "protocol": "tcp", "port": 3306, "status": "connected"}]}, "timestamp": "..."}
```

and append to the same block:

```json
{"type": "infrastructure_link_update", "payload": {"link_id": "ecs-aurora", "status": "disconnecting|disconnected|restoring|connected|error", "message": "...", "request_id": "<uuid, echoed only when the client sent one>"}, "timestamp": "..."}
```

- [x] **Step 2: Add the client message**

In `### Client → Server`, add:

```json
{"type": "break_database", "payload": {}}
{"type": "break_database", "payload": {"request_id": "<uuid>", "source": "datacenter_3d", "link_id": "ecs-aurora"}}
```

- [x] **Step 3: Add a short section after `## Phase State Machine`**

```markdown
## Infrastructure Link State

`ecs-aurora` mirrors the real RDS security-group ingress rule (TCP/3306 from the ECS SG).

- Break: `disconnecting` → `disconnected` (then the normal incident flow), or `disconnecting` → `error` (link returns to `connected`, no incident).
- A `break_database` received while `disconnecting` is ignored.
- Reset and voice-agent remediation: `restoring` → `connected`, or `restoring` → `error` (link stays `disconnected`).
- Clients must not commit cable visuals until they receive `disconnected` / `connected`.
```

- [x] **Step 4: Commit**

```bash
git add docs/frontend/api-contract.md
git commit -m "docs: document infrastructure_link_update and break_database request_id"
```

---

## Task 5: Frontend dependencies, Vitest config and the `/datacenter` route

**Files:**
- Modify: `src_frontend/app/package.json`
- Modify: `src_frontend/app/vite.config.ts`
- Modify: `src_frontend/app/src/app/main.tsx`
- Create: `src_frontend/app/src/datacenter/DataCenterPage.tsx` (placeholder, replaced in Task 12)

- [x] **Step 1: Add dependencies**

Run from `src_frontend/app`:

```bash
npm install three@^0.169.0 @react-three/fiber@^8.17.0 @react-three/drei@^9.114.0
npm install -D @types/three@^0.169.0
```

Fiber 9 and drei 10 require React 19; stay on the 8.x / 9.x lines. Confirm `package.json` shows the four new entries.

- [x] **Step 2: Enable Vitest in `vite.config.ts`**

Add as the first line of the file:

```ts
/// <reference types="vitest" />
```

and add to the `defineConfig({...})` object, after `server`:

```ts
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
```

- [x] **Step 3: Create the placeholder page**

Create `src_frontend/app/src/datacenter/DataCenterPage.tsx`:

```tsx
export function DataCenterPage() {
  return <div style={{ color: "#fff", padding: 24 }}>Data center view — loading scene…</div>;
}
```

- [x] **Step 4: Add routing in `main.tsx`**

Replace the file with:

```tsx
import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { App } from "./App";
// Register the link-store WebSocket handler eagerly so the connect-time system_status is not
// missed while the lazy /datacenter chunk is still loading.
import "@/store/infrastructureStore";

const DataCenterPage = lazy(() =>
  import("@/datacenter/DataCenterPage").then((m) => ({ default: m.DataCenterPage })),
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route
          path="/datacenter"
          element={
            <Suspense fallback={<div style={{ color: "#fff", padding: 24 }}>Loading data center…</div>}>
              <DataCenterPage />
            </Suspense>
          }
        />
        <Route path="*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
```

`path="*"` keeps `/` and every other path rendering the existing UI exactly as before.

- [x] **Step 5: Verify**

Run: `cd src_frontend/app && npm run build`
Expected: succeeds; `ls dist/assets` shows a separate `DataCenterPage-*.js` chunk.

Run: `npm run dev`, open `http://localhost:3000/` (existing city renders, DevPanel works) and `http://localhost:3000/datacenter` (placeholder text).

- [x] **Step 6: Commit**

```bash
git add package.json package-lock.json vite.config.ts src/app/main.tsx src/datacenter/DataCenterPage.tsx
git commit -m "feat(frontend): add lazy /datacenter route and 3D dependencies"
```

---

## Task 6: Shared infrastructure link store

**Files:**
- Create: `src_frontend/app/src/types/infrastructure.ts`
- Create: `src_frontend/app/src/store/infrastructureStore.ts`
- Create: `src_frontend/app/src/store/infrastructureStore.test.ts`

- [x] **Step 1: Write the types**

Create `src_frontend/app/src/types/infrastructure.ts`:

```ts
export type LinkStatus = "connected" | "disconnecting" | "disconnected" | "restoring";

export interface InfrastructureLink {
  id: string;
  source: string;
  target: string;
  protocol: string;
  port: number;
  status: LinkStatus;
}

export interface LinkUpdatePayload {
  link_id: string;
  status: LinkStatus | "error";
  request_id?: string;
  message?: string;
}
```

- [x] **Step 2: Write the failing tests**

Create `src_frontend/app/src/store/infrastructureStore.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/websocket", () => ({ subscribe: vi.fn(), send: vi.fn() }));

import { send } from "@/lib/websocket";
import { useSceneStore } from "@/store/sceneStore";
import { ECS_AURORA_LINK, canDisconnect, useInfrastructureStore } from "@/store/infrastructureStore";

beforeEach(() => {
  useInfrastructureStore.setState({
    link: ECS_AURORA_LINK,
    pendingRequestId: null,
    lastError: null,
    lastMessage: "",
  });
  useSceneStore.setState({ state: "HEALTHY" });
  vi.mocked(send).mockClear();
});

describe("requestDisconnect", () => {
  it("sends break_database with a request id and marks it pending", () => {
    const id = useInfrastructureStore.getState().requestDisconnect();
    expect(id).toBeTruthy();
    expect(useInfrastructureStore.getState().pendingRequestId).toBe(id);
    expect(send).toHaveBeenCalledWith({
      type: "break_database",
      payload: { request_id: id, source: "datacenter_3d", link_id: "ecs-aurora" },
    });
  });

  it("refuses when the phase is not HEALTHY", () => {
    useSceneStore.setState({ state: "DIAGNOSING" });
    expect(useInfrastructureStore.getState().requestDisconnect()).toBeNull();
    expect(send).not.toHaveBeenCalled();
  });

  it("refuses while a request is pending", () => {
    useInfrastructureStore.getState().requestDisconnect();
    expect(useInfrastructureStore.getState().requestDisconnect()).toBeNull();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("refuses when the link is not connected", () => {
    useInfrastructureStore.setState({ link: { ...ECS_AURORA_LINK, status: "disconnected" } });
    expect(useInfrastructureStore.getState().requestDisconnect()).toBeNull();
  });
});

describe("applyUpdate", () => {
  it("keeps the pending id on disconnecting and clears it on disconnected", () => {
    const id = useInfrastructureStore.getState().requestDisconnect()!;
    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "disconnecting", request_id: id });
    expect(useInfrastructureStore.getState().pendingRequestId).toBe(id);
    expect(useInfrastructureStore.getState().link.status).toBe("disconnecting");

    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "disconnected", request_id: id, message: "removed" });
    expect(useInfrastructureStore.getState().pendingRequestId).toBeNull();
    expect(useInfrastructureStore.getState().link.status).toBe("disconnected");
    expect(useInfrastructureStore.getState().lastMessage).toBe("removed");
  });

  it("rolls back disconnecting to connected on error and records the message", () => {
    useInfrastructureStore.getState().requestDisconnect();
    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "disconnecting" });
    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "error", message: "boom" });
    const s = useInfrastructureStore.getState();
    expect(s.link.status).toBe("connected");
    expect(s.pendingRequestId).toBeNull();
    expect(s.lastError).toBe("boom");
  });

  it("rolls back restoring to disconnected on error", () => {
    useInfrastructureStore.setState({ link: { ...ECS_AURORA_LINK, status: "restoring" } });
    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "error", message: "denied" });
    expect(useInfrastructureStore.getState().link.status).toBe("disconnected");
  });

  it("ignores updates for other links", () => {
    useInfrastructureStore.getState().applyUpdate({ link_id: "other", status: "disconnected" });
    expect(useInfrastructureStore.getState().link.status).toBe("connected");
  });
});

describe("hydrate", () => {
  it("adopts the matching link from system_status and clears pending", () => {
    useInfrastructureStore.getState().requestDisconnect();
    useInfrastructureStore.getState().hydrate([{ ...ECS_AURORA_LINK, status: "disconnected" }]);
    expect(useInfrastructureStore.getState().link.status).toBe("disconnected");
    expect(useInfrastructureStore.getState().pendingRequestId).toBeNull();
  });
});

describe("canDisconnect", () => {
  it("is true only when HEALTHY, connected and idle", () => {
    expect(canDisconnect("HEALTHY", ECS_AURORA_LINK, null)).toBe(true);
    expect(canDisconnect("CALLING", ECS_AURORA_LINK, null)).toBe(false);
    expect(canDisconnect("HEALTHY", { ...ECS_AURORA_LINK, status: "restoring" }, null)).toBe(false);
    expect(canDisconnect("HEALTHY", ECS_AURORA_LINK, "req")).toBe(false);
  });
});
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd src_frontend/app && npm test -- --run src/store/infrastructureStore.test.ts`
Expected: FAIL, cannot resolve `@/store/infrastructureStore`

- [x] **Step 4: Write the store**

Create `src_frontend/app/src/store/infrastructureStore.ts`:

```ts
import { create } from "zustand";
import { subscribe, send } from "@/lib/websocket";
import type { WsMessage } from "@/lib/websocket";
import { useSceneStore } from "@/store/sceneStore";
import type { InfrastructureLink, LinkStatus, LinkUpdatePayload } from "@/types/infrastructure";
import type { SceneState } from "@/types/scene";

export const ECS_AURORA_LINK: InfrastructureLink = {
  id: "ecs-aurora",
  source: "ecs-cluster",
  target: "aurora-db",
  protocol: "tcp",
  port: 3306,
  status: "connected",
};

const ROLLBACK: Partial<Record<LinkStatus, LinkStatus>> = {
  disconnecting: "connected",
  restoring: "disconnected",
};

export function canDisconnect(phase: SceneState, link: InfrastructureLink, pendingRequestId: string | null): boolean {
  return phase === "HEALTHY" && link.status === "connected" && pendingRequestId === null;
}

interface InfrastructureStore {
  link: InfrastructureLink;
  pendingRequestId: string | null;
  lastError: string | null;
  lastMessage: string;
  requestDisconnect: () => string | null;
  applyUpdate: (payload: LinkUpdatePayload) => void;
  hydrate: (links: InfrastructureLink[]) => void;
  clearError: () => void;
}

export const useInfrastructureStore = create<InfrastructureStore>((set, get) => ({
  link: ECS_AURORA_LINK,
  pendingRequestId: null,
  lastError: null,
  lastMessage: "",

  requestDisconnect: () => {
    const { link, pendingRequestId } = get();
    if (!canDisconnect(useSceneStore.getState().state, link, pendingRequestId)) return null;
    const requestId = crypto.randomUUID();
    set({ pendingRequestId: requestId, lastError: null });
    send({
      type: "break_database",
      payload: { request_id: requestId, source: "datacenter_3d", link_id: link.id },
    });
    return requestId;
  },

  applyUpdate: (payload) => {
    const { link, pendingRequestId } = get();
    if (payload.link_id !== link.id) return;
    if (payload.status === "error") {
      set({
        link: { ...link, status: ROLLBACK[link.status] ?? link.status },
        pendingRequestId: null,
        lastError: payload.message ?? "AWS operation failed",
      });
      return;
    }
    set({
      link: { ...link, status: payload.status },
      lastMessage: payload.message ?? "",
      pendingRequestId: payload.status === "disconnecting" ? pendingRequestId : null,
    });
  },

  hydrate: (links) => {
    const match = links.find((l) => l.id === get().link.id);
    if (match) set({ link: match, pendingRequestId: null });
  },

  clearError: () => set({ lastError: null }),
}));

function handleWsMessage(message: WsMessage): void {
  const { type, payload } = message;
  if (!payload) return;
  if (type === "infrastructure_link_update") {
    useInfrastructureStore.getState().applyUpdate(payload as unknown as LinkUpdatePayload);
  }
  if (type === "system_status" && Array.isArray(payload.infrastructure_links)) {
    useInfrastructureStore.getState().hydrate(payload.infrastructure_links as InfrastructureLink[]);
  }
}

subscribe(handleWsMessage);
```

- [x] **Step 5: Run tests to verify they pass**

Run: `npm test -- --run src/store/infrastructureStore.test.ts`
Expected: 10 tests PASS

- [x] **Step 6: Commit**

```bash
git add src/types/infrastructure.ts src/store/infrastructureStore.ts src/store/infrastructureStore.test.ts
git commit -m "feat(frontend): add shared infrastructure link store driven by backend acknowledgements"
```

---

## Task 7: World layout and collision

**Files:**
- Create: `src_frontend/app/src/datacenter/lib/collision.ts`
- Create: `src_frontend/app/src/datacenter/lib/collision.test.ts`
- Create: `src_frontend/app/src/datacenter/config/layout.ts`

Units: 1 Three.js unit = 1 metre. Room is 30 m wide (x ∈ [-15, 15]) by 40 m deep (z ∈ [-20, 20]). Camera looks toward −z at yaw 0. Player spawns at the front (z = 14) facing the racks; the NOC wall is on the back wall (z = −19.7). Four rows of 14 racks; the row at z = 3 holds the four hero racks.

- [x] **Step 1: Write the failing collision tests**

Create `src_frontend/app/src/datacenter/lib/collision.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { resolveMove, type Box, type Bounds } from "@/datacenter/lib/collision";

const bounds: Bounds = { minX: -10, maxX: 10, minZ: -10, maxZ: 10 };
const rack: Box = { minX: -1, maxX: 1, minZ: -0.5, maxZ: 0.5 };

describe("resolveMove", () => {
  it("moves freely when nothing is in the way", () => {
    expect(resolveMove(0, 5, 1, -1, [rack], bounds)).toEqual({ x: 1, z: 4 });
  });

  it("stops in front of a box instead of entering it", () => {
    const r = resolveMove(0, 1.2, 0, -0.5, [rack], bounds);
    expect(r.z).toBe(1.2);
  });

  it("slides along a box when moving diagonally into it", () => {
    const r = resolveMove(0, 1.2, 0.5, -0.5, [rack], bounds);
    expect(r).toEqual({ x: 0.5, z: 1.2 });
  });

  it("clamps to the room bounds", () => {
    expect(resolveMove(9.9, 0, 5, 0, [], bounds)).toEqual({ x: 10, z: 0 });
    expect(resolveMove(0, -9.9, 0, -5, [], bounds)).toEqual({ x: 0, z: -10 });
  });
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd src_frontend/app && npm test -- --run src/datacenter/lib/collision.test.ts`
Expected: FAIL, module not found

- [x] **Step 3: Write `collision.ts`**

```ts
export interface Box {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
}

export type Bounds = Box;

const PLAYER_RADIUS = 0.35;

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

function hitsAny(x: number, z: number, boxes: Box[]): boolean {
  return boxes.some(
    (b) =>
      x + PLAYER_RADIUS > b.minX &&
      x - PLAYER_RADIUS < b.maxX &&
      z + PLAYER_RADIUS > b.minZ &&
      z - PLAYER_RADIUS < b.maxZ,
  );
}

/** Axis-separated AABB slide: try X, then Z, so the player glides along rack faces. */
export function resolveMove(
  x: number,
  z: number,
  dx: number,
  dz: number,
  boxes: Box[],
  bounds: Bounds,
): { x: number; z: number } {
  let nx = clamp(x + dx, bounds.minX, bounds.maxX);
  if (hitsAny(nx, z, boxes)) nx = x;
  let nz = clamp(z + dz, bounds.minZ, bounds.maxZ);
  if (hitsAny(nx, nz, boxes)) nz = z;
  return { x: nx, z: nz };
}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `npm test -- --run src/datacenter/lib/collision.test.ts`
Expected: 4 PASS

- [x] **Step 5: Write `layout.ts`**

Create `src_frontend/app/src/datacenter/config/layout.ts`:

```ts
import type { Box, Bounds } from "@/datacenter/lib/collision";

export type Vec3 = [number, number, number];

export const ROOM = { width: 30, depth: 40, height: 4.2 } as const;
export const RACK = { width: 0.8, height: 2.2, depth: 1.2 } as const;
const RACK_PITCH = 1.0;
const RACKS_PER_ROW = 14;
export const ROW_Z: readonly number[] = [-9, -3, 3, 9];
export const HERO_ROW_Z = 3;

export interface HeroRack {
  id: string; // backend service name, so metrics map automatically
  label: string;
  x: number;
  z: number;
}

export const HERO_RACKS: HeroRack[] = [
  { id: "ecs-cluster", label: "ECS APPLICATION TIER", x: -3.5, z: HERO_ROW_Z },
  { id: "network", label: "NETWORK CONTROL · SG POLICY", x: -0.5, z: HERO_ROW_Z },
  { id: "aurora-db", label: "AURORA MYSQL · PRODUCTION", x: 3.5, z: HERO_ROW_Z },
  { id: "monitoring", label: "CLOUDWATCH · MONITORING", x: 6.5, z: HERO_ROW_Z },
];

export interface RackPosition {
  x: number;
  z: number;
}

const ROW_XS: number[] = Array.from({ length: RACKS_PER_ROW }, (_, i) => -6.5 + i * RACK_PITCH);

/** All rack slots except the four hero positions. */
export const FILLER_RACKS: RackPosition[] = ROW_Z.flatMap((z) =>
  ROW_XS.filter((x) => !(z === HERO_ROW_Z && HERO_RACKS.some((h) => h.x === x))).map((x) => ({ x, z })),
);

/** Each row is one solid collision slab. */
export const RACK_BOXES: Box[] = ROW_Z.map((z) => ({
  minX: ROW_XS[0] - RACK.width / 2,
  maxX: ROW_XS[ROW_XS.length - 1] + RACK.width / 2,
  minZ: z - RACK.depth / 2,
  maxZ: z + RACK.depth / 2,
}));

export const WALK_BOUNDS: Bounds = { minX: -14.5, maxX: 14.5, minZ: -19.5, maxZ: 19.5 };

export const PLAYER = { eyeHeight: 1.7, spawn: [0, 1.7, 14] as Vec3, spawnYaw: 0 } as const;

/** Cable: ECS rack front-top → floor service bridge → Aurora rack front-top. */
export const LINK_POINTS: Vec3[] = [
  [-3.5, 1.6, 3.62],
  [-3.3, 0.9, 4.0],
  [-2.0, 0.18, 4.4],
  [0, 0.18, 4.6],
  [2.0, 0.18, 4.4],
  [3.3, 0.9, 4.0],
  [3.5, 1.6, 3.62],
];

export const LINK_TARGET = { position: [0, 1.2, 4.6] as Vec3, size: [1.2, 2.4, 0.7] as Vec3 };
/** Where the "G" key places the player: in front of the bridge, facing −z. */
export const LINK_STAND_POINT = { position: [0, 1.7, 7.0] as Vec3, yaw: 0 };

export const NOC_WALL = { position: [0, 2.2, -19.7] as Vec3, width: 10, height: 3, htmlScale: 0.4 };
```

- [x] **Step 6: Type-check and commit**

Run: `npx tsc --noEmit`
Expected: no errors

```bash
git add src/datacenter/lib/collision.ts src/datacenter/lib/collision.test.ts src/datacenter/config/layout.ts
git commit -m "feat(datacenter): world layout constants and AABB collision"
```

---

## Task 8: Camera director, hold-to-confirm and the 3D UI store

**Files:**
- Create: `src_frontend/app/src/datacenter/lib/cameraDirector.ts` (+ `.test.ts`)
- Create: `src_frontend/app/src/datacenter/lib/holdToConfirm.ts` (+ `.test.ts`)
- Create: `src_frontend/app/src/datacenter/store/dataCenterUiStore.ts` (+ `.test.ts`)

- [x] **Step 1: Write the failing camera-director test**

Create `src_frontend/app/src/datacenter/lib/cameraDirector.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { shotForPhase } from "@/datacenter/lib/cameraDirector";
import type { SceneState } from "@/types/scene";

const PHASES: SceneState[] = ["HEALTHY", "INCIDENT_DETECTED", "DIAGNOSING", "CALLING", "RECOVERING", "RESOLVED"];

describe("shotForPhase", () => {
  it("orbits slowly while HEALTHY", () => {
    const a = shotForPhase("HEALTHY", 0);
    const b = shotForPhase("HEALTHY", 10);
    expect(a.position).not.toEqual(b.position);
    const r = Math.hypot(a.position[0], a.position[2]);
    expect(r).toBeCloseTo(13, 5);
  });

  it("holds a fixed shot in every incident phase", () => {
    for (const p of PHASES.filter((p) => p !== "HEALTHY")) {
      expect(shotForPhase(p, 0)).toEqual(shotForPhase(p, 42));
    }
  });

  it("keeps the camera inside the room", () => {
    for (const p of PHASES) {
      const { position } = shotForPhase(p, 7);
      expect(Math.abs(position[0])).toBeLessThan(15);
      expect(Math.abs(position[2])).toBeLessThan(20);
      expect(position[1]).toBeGreaterThan(0.5);
      expect(position[1]).toBeLessThan(4.2);
    }
  });
});
```

- [x] **Step 2: Write `cameraDirector.ts`**

```ts
import type { Vec3 } from "@/datacenter/config/layout";
import type { SceneState } from "@/types/scene";

export interface Shot {
  position: Vec3;
  target: Vec3;
}

const AURORA_RACK: Vec3 = [3.5, 1.2, 3];
const LINK_BRIDGE: Vec3 = [0, 0.4, 4.6];
const NOC_SCREEN: Vec3 = [0, 2.2, -19.7];
const ORBIT_RADIUS = 13;
const ORBIT_SPEED = 0.08;

/** Phase-driven cinematic camera. `t` is elapsed seconds. */
export function shotForPhase(phase: SceneState, t: number): Shot {
  switch (phase) {
    case "HEALTHY": {
      const a = t * ORBIT_SPEED;
      return { position: [Math.sin(a) * ORBIT_RADIUS, 3.8, Math.cos(a) * ORBIT_RADIUS], target: [0, 1, 0] };
    }
    case "INCIDENT_DETECTED":
    case "DIAGNOSING":
      return { position: [1.5, 2.4, 7.4], target: AURORA_RACK };
    case "CALLING":
      return { position: [0, 2.6, -11], target: NOC_SCREEN };
    case "RECOVERING":
      return { position: [0.8, 2.4, 7.6], target: LINK_BRIDGE };
    case "RESOLVED":
      return { position: [0, 3.6, 15], target: [0, 1, -2] };
  }
}
```

- [x] **Step 3: Write the failing hold-to-confirm test**

Create `src_frontend/app/src/datacenter/lib/holdToConfirm.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { HOLD_DURATION_S, initialHold, reduceHold } from "@/datacenter/lib/holdToConfirm";

describe("reduceHold", () => {
  it("starts holding on press with zero progress", () => {
    const { state, confirmed } = reduceHold(initialHold, { type: "press" });
    expect(state).toEqual({ holding: true, progress: 0 });
    expect(confirmed).toBe(false);
  });

  it("accumulates progress while holding", () => {
    const held = reduceHold(initialHold, { type: "press" }).state;
    const { state } = reduceHold(held, { type: "tick", dt: HOLD_DURATION_S / 2 });
    expect(state.progress).toBeCloseTo(0.5);
  });

  it("does not progress when not holding", () => {
    const { state } = reduceHold(initialHold, { type: "tick", dt: 5 });
    expect(state).toEqual(initialHold);
  });

  it("confirms once when the hold completes and resets", () => {
    const held = reduceHold(initialHold, { type: "press" }).state;
    const { state, confirmed } = reduceHold(held, { type: "tick", dt: HOLD_DURATION_S + 0.1 });
    expect(confirmed).toBe(true);
    expect(state).toEqual(initialHold);
  });

  it("release and cancel reset without confirming", () => {
    const held = reduceHold(reduceHold(initialHold, { type: "press" }).state, { type: "tick", dt: 1 }).state;
    expect(reduceHold(held, { type: "release" })).toEqual({ state: initialHold, confirmed: false });
    expect(reduceHold(held, { type: "cancel" })).toEqual({ state: initialHold, confirmed: false });
  });
});
```

- [x] **Step 4: Write `holdToConfirm.ts`**

```ts
export const HOLD_DURATION_S = 1.25;

export interface HoldState {
  holding: boolean;
  /** 0..1 */
  progress: number;
}

export type HoldEvent =
  | { type: "press" }
  | { type: "release" }
  | { type: "cancel" }
  | { type: "tick"; dt: number };

export interface HoldResult {
  state: HoldState;
  confirmed: boolean;
}

export const initialHold: HoldState = { holding: false, progress: 0 };

export function reduceHold(state: HoldState, event: HoldEvent): HoldResult {
  switch (event.type) {
    case "press":
      return { state: { holding: true, progress: 0 }, confirmed: false };
    case "release":
    case "cancel":
      return { state: initialHold, confirmed: false };
    case "tick": {
      if (!state.holding) return { state, confirmed: false };
      const progress = state.progress + event.dt / HOLD_DURATION_S;
      if (progress >= 1) return { state: initialHold, confirmed: true };
      return { state: { holding: true, progress }, confirmed: false };
    }
  }
}
```

- [x] **Step 5: Write the failing UI store test**

Create `src_frontend/app/src/datacenter/store/dataCenterUiStore.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/websocket", () => ({ subscribe: vi.fn(), send: vi.fn() }));

import { send } from "@/lib/websocket";
import { initialHold } from "@/datacenter/lib/holdToConfirm";
import { useDataCenterUiStore } from "@/datacenter/store/dataCenterUiStore";
import { ECS_AURORA_LINK, useInfrastructureStore } from "@/store/infrastructureStore";
import { useSceneStore } from "@/store/sceneStore";

beforeEach(() => {
  useDataCenterUiStore.setState({ mode: "director", lookingAtLink: false, hold: initialHold, panelOpen: true });
  useInfrastructureStore.setState({ link: ECS_AURORA_LINK, pendingRequestId: null, lastError: null, lastMessage: "" });
  useSceneStore.setState({ state: "HEALTHY" });
  vi.mocked(send).mockClear();
});

describe("dataCenterUiStore", () => {
  it("toggles camera mode", () => {
    useDataCenterUiStore.getState().toggleMode();
    expect(useDataCenterUiStore.getState().mode).toBe("walk");
    useDataCenterUiStore.getState().toggleMode();
    expect(useDataCenterUiStore.getState().mode).toBe("director");
  });

  it("sends exactly one break_database when a hold completes", () => {
    const s = useDataCenterUiStore.getState();
    s.holdDispatch({ type: "press" });
    for (let i = 0; i < 20; i++) s.holdDispatch({ type: "tick", dt: 0.1 });
    expect(send).toHaveBeenCalledTimes(1);
    expect(vi.mocked(send).mock.calls[0][0].type).toBe("break_database");
    expect(useDataCenterUiStore.getState().hold).toEqual(initialHold);
  });

  it("does not send when released early", () => {
    const s = useDataCenterUiStore.getState();
    s.holdDispatch({ type: "press" });
    s.holdDispatch({ type: "tick", dt: 0.5 });
    s.holdDispatch({ type: "release" });
    expect(send).not.toHaveBeenCalled();
  });
});
```

- [x] **Step 6: Write `dataCenterUiStore.ts`**

```ts
import { create } from "zustand";
import { initialHold, reduceHold, type HoldEvent, type HoldState } from "@/datacenter/lib/holdToConfirm";
import { useInfrastructureStore } from "@/store/infrastructureStore";

export type CameraMode = "director" | "walk";

interface DataCenterUiStore {
  mode: CameraMode;
  lookingAtLink: boolean;
  hold: HoldState;
  panelOpen: boolean;
  setMode: (mode: CameraMode) => void;
  toggleMode: () => void;
  setLookingAtLink: (looking: boolean) => void;
  togglePanel: () => void;
  holdDispatch: (event: HoldEvent) => void;
}

export const useDataCenterUiStore = create<DataCenterUiStore>((set, get) => ({
  mode: "director",
  lookingAtLink: false,
  hold: initialHold,
  panelOpen: true,

  setMode: (mode) => set({ mode }),
  toggleMode: () => set({ mode: get().mode === "director" ? "walk" : "director" }),
  setLookingAtLink: (looking) => set({ lookingAtLink: looking }),
  togglePanel: () => set({ panelOpen: !get().panelOpen }),

  holdDispatch: (event) => {
    const { state, confirmed } = reduceHold(get().hold, event);
    set({ hold: state });
    if (confirmed) useInfrastructureStore.getState().requestDisconnect();
  },
}));
```

- [x] **Step 7: Run all frontend tests**

Run: `npm test -- --run`
Expected: collision (4), cameraDirector (3), holdToConfirm (5), dataCenterUiStore (3), infrastructureStore (10) all PASS

- [x] **Step 8: Commit**

```bash
git add src/datacenter/lib src/datacenter/store
git commit -m "feat(datacenter): camera director, hold-to-confirm reducer and 3D UI store"
```

---

## Task 9: Facility shell and instanced rack rows

**Files:**
- Create: `src_frontend/app/src/datacenter/scene/Facility.tsx`
- Create: `src_frontend/app/src/datacenter/scene/RackRows.tsx`

These are visual components; there are no unit tests. Verification is by eye in Task 12. Keep `npx tsc --noEmit` clean after each file.

- [x] **Step 1: Write `Facility.tsx`**

```tsx
import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { PointLight } from "three";
import { ROOM } from "@/datacenter/config/layout";
import { useSceneStore } from "@/store/sceneStore";

const HALF_W = ROOM.width / 2;
const HALF_D = ROOM.depth / 2;
const CEILING_LIGHT_Z = [-16, -8, 0, 8, 16];
const WALL_COLOR = "#23272c";

export function Facility() {
  const phase = useSceneStore((s) => s.state);
  const alarmRef = useRef<PointLight>(null);

  const alarm = phase === "INCIDENT_DETECTED" || phase === "DIAGNOSING" || phase === "CALLING";
  const amber = phase === "RECOVERING";

  useFrame(({ clock }) => {
    const light = alarmRef.current;
    if (!light) return;
    if (alarm) light.intensity = 40 + Math.sin(clock.elapsedTime * 6) * 35;
    else if (amber) light.intensity = 25;
    else light.intensity = 0;
  });

  return (
    <>
      <color attach="background" args={["#07090c"]} />
      <fog attach="fog" args={["#07090c", 6, 48]} />
      <ambientLight intensity={0.35} />
      {CEILING_LIGHT_Z.map((z) => (
        <pointLight
          key={z}
          position={[0, ROOM.height - 0.2, z]}
          intensity={alarm ? 60 : 140}
          distance={26}
          decay={2}
          color={alarm ? "#ffb4a8" : "#dfe8ff"}
        />
      ))}
      {/* Alarm strobe above the hero row */}
      <pointLight
        ref={alarmRef}
        position={[0, 3.6, 3]}
        distance={20}
        decay={2}
        color={amber ? "#ffb300" : "#ff1f1f"}
        intensity={0}
      />

      {/* Floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[ROOM.width, ROOM.depth]} />
        <meshStandardMaterial color="#1c1f23" roughness={0.85} metalness={0.15} />
      </mesh>
      {/* Safety stripes marking the hero aisle */}
      {[4.9, 7.1].map((z) => (
        <mesh key={z} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, z]}>
          <planeGeometry args={[14, 0.08]} />
          <meshStandardMaterial color="#e6b400" roughness={0.6} />
        </mesh>
      ))}

      {/* Ceiling */}
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, ROOM.height, 0]}>
        <planeGeometry args={[ROOM.width, ROOM.depth]} />
        <meshStandardMaterial color="#0d1014" roughness={1} />
      </mesh>

      {/* Walls */}
      <mesh position={[0, ROOM.height / 2, -HALF_D]}>
        <boxGeometry args={[ROOM.width, ROOM.height, 0.2]} />
        <meshStandardMaterial color={WALL_COLOR} roughness={0.9} />
      </mesh>
      <mesh position={[0, ROOM.height / 2, HALF_D]}>
        <boxGeometry args={[ROOM.width, ROOM.height, 0.2]} />
        <meshStandardMaterial color={WALL_COLOR} roughness={0.9} />
      </mesh>
      <mesh position={[-HALF_W, ROOM.height / 2, 0]}>
        <boxGeometry args={[0.2, ROOM.height, ROOM.depth]} />
        <meshStandardMaterial color={WALL_COLOR} roughness={0.9} />
      </mesh>
      <mesh position={[HALF_W, ROOM.height / 2, 0]}>
        <boxGeometry args={[0.2, ROOM.height, ROOM.depth]} />
        <meshStandardMaterial color={WALL_COLOR} roughness={0.9} />
      </mesh>
    </>
  );
}
```

Light intensities assume three r155+ physically-based units (candela). If the room looks dark or blown out on the booth laptop, scale all `intensity` values together.

- [x] **Step 2: Write `RackRows.tsx`**

```tsx
import { useLayoutEffect, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Color, InstancedMesh, Object3D } from "three";
import { FILLER_RACKS, RACK } from "@/datacenter/config/layout";

const LEDS_PER_RACK = 8;
const LED_GREEN = new Color("#22c55e");
const LED_CYAN = new Color("#22d3ee");
const LED_OFF = new Color("#0a3d1a");
const BLINK_INTERVAL_S = 0.12;
const BLINKS_PER_INTERVAL = 40;
const dummy = new Object3D();

function baseColor(k: number): Color {
  return k % 2 === 0 ? LED_GREEN : LED_CYAN;
}

export function RackRows() {
  const rackRef = useRef<InstancedMesh>(null);
  const ledRef = useRef<InstancedMesh>(null);
  const nextBlink = useRef(0);
  const ledCount = FILLER_RACKS.length * LEDS_PER_RACK;

  useLayoutEffect(() => {
    const racks = rackRef.current;
    const leds = ledRef.current;
    if (!racks || !leds) return;
    FILLER_RACKS.forEach((r, i) => {
      dummy.position.set(r.x, RACK.height / 2, r.z);
      dummy.updateMatrix();
      racks.setMatrixAt(i, dummy.matrix);
      for (let j = 0; j < LEDS_PER_RACK; j++) {
        const k = i * LEDS_PER_RACK + j;
        dummy.position.set(
          r.x - 0.28 + (j % 2) * 0.56,
          0.4 + Math.floor(j / 2) * 0.45,
          r.z + RACK.depth / 2 + 0.006,
        );
        dummy.updateMatrix();
        leds.setMatrixAt(k, dummy.matrix);
        leds.setColorAt(k, baseColor(k));
      }
    });
    racks.instanceMatrix.needsUpdate = true;
    leds.instanceMatrix.needsUpdate = true;
    if (leds.instanceColor) leds.instanceColor.needsUpdate = true;
  }, []);

  useFrame(({ clock }) => {
    const leds = ledRef.current;
    if (!leds || clock.elapsedTime < nextBlink.current) return;
    nextBlink.current = clock.elapsedTime + BLINK_INTERVAL_S;
    for (let n = 0; n < BLINKS_PER_INTERVAL; n++) {
      const k = Math.floor(Math.random() * ledCount);
      leds.setColorAt(k, Math.random() < 0.15 ? LED_OFF : baseColor(k));
    }
    if (leds.instanceColor) leds.instanceColor.needsUpdate = true;
  });

  return (
    <group>
      <instancedMesh ref={rackRef} args={[undefined, undefined, FILLER_RACKS.length]}>
        <boxGeometry args={[RACK.width, RACK.height, RACK.depth]} />
        <meshStandardMaterial color="#15181c" metalness={0.65} roughness={0.35} />
      </instancedMesh>
      <instancedMesh ref={ledRef} args={[undefined, undefined, ledCount]}>
        <boxGeometry args={[0.04, 0.04, 0.01]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
    </group>
  );
}
```

`meshBasicMaterial` is deliberate: LEDs are unlit emitters and the per-instance colour set via `setColorAt` multiplies the material's white. `toneMapped={false}` keeps them saturated under ACES tone mapping.

- [x] **Step 3: Type-check and commit**

Run: `npx tsc --noEmit`
Expected: no errors

```bash
git add src/datacenter/scene/Facility.tsx src/datacenter/scene/RackRows.tsx
git commit -m "feat(datacenter): facility shell with alarm lighting and instanced rack rows"
```

---

## Task 10: Hero racks, the service cable and the NOC wall

**Files:**
- Create: `src_frontend/app/src/datacenter/scene/HeroRack.tsx`
- Create: `src_frontend/app/src/datacenter/scene/ServiceLink.tsx`
- Create: `src_frontend/app/src/datacenter/scene/NocWall.tsx`

- [x] **Step 1: Write `HeroRack.tsx`**

```tsx
import { Html } from "@react-three/drei";
import { RACK, type HeroRack as HeroRackConfig } from "@/datacenter/config/layout";
import { useInfrastructureStore } from "@/store/infrastructureStore";
import { useMetricsStore } from "@/store/metricsStore";
import { useSceneStore } from "@/store/sceneStore";

type RackHealth = "healthy" | "alert" | "recovering";

const PANEL_COLORS: Record<RackHealth, string> = {
  healthy: "#16a34a",
  alert: "#dc2626",
  recovering: "#f59e0b",
};

function useRackHealth(id: string): RackHealth {
  const phase = useSceneStore((s) => s.state);
  const affected = useSceneStore((s) => s.affectedService);
  if (affected !== id || phase === "HEALTHY") return "healthy";
  if (phase === "RECOVERING" || phase === "RESOLVED") return "recovering";
  return "alert";
}

function last(values: number[] | undefined): number {
  return values && values.length > 0 ? Math.round(values[values.length - 1]) : 0;
}

const RULE_TEXT: Record<string, string> = {
  connected: "ALLOW ECS_SG → RDS_SG TCP/3306",
  disconnecting: "REVOKING RULE…",
  disconnected: "RULE MISSING",
  restoring: "RESTORING RULE…",
};

export function HeroRack({ rack }: { rack: HeroRackConfig }) {
  const health = useRackHealth(rack.id);
  const metrics = useMetricsStore((s) => s.metrics[rack.id]);
  const linkStatus = useInfrastructureStore((s) => s.link.status);

  return (
    <group position={[rack.x, 0, rack.z]}>
      <mesh position={[0, RACK.height / 2, 0]}>
        <boxGeometry args={[RACK.width, RACK.height, RACK.depth]} />
        <meshStandardMaterial color="#1a1e23" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* Front status panel */}
      <mesh position={[0, 1.2, RACK.depth / 2 + 0.006]}>
        <planeGeometry args={[0.6, 1.6]} />
        <meshStandardMaterial
          color="#0b0d10"
          emissive={PANEL_COLORS[health]}
          emissiveIntensity={health === "healthy" ? 0.35 : 1.2}
        />
      </mesh>
      <Html
        position={[0, RACK.height + 0.45, RACK.depth / 2]}
        center
        distanceFactor={7}
        zIndexRange={[10, 0]}
        style={{ pointerEvents: "none" }}
      >
        <div className={`dc-rack-label dc-rack-label--${health}`}>
          <div className="dc-rack-title">{rack.label}</div>
          <div className="dc-rack-metrics">
            {rack.id === "network"
              ? RULE_TEXT[linkStatus]
              : `CPU ${last(metrics?.cpu)}% · MEM ${last(metrics?.mem)}% · IOPS ${last(metrics?.iops)}`}
          </div>
          <div className="dc-rack-status">{health.toUpperCase()}</div>
        </div>
      </Html>
    </group>
  );
}
```

- [x] **Step 2: Write `ServiceLink.tsx`**

```tsx
import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { CatmullRomCurve3, Group, MeshStandardMaterial, TubeGeometry, Vector3 } from "three";
import { LINK_POINTS, LINK_TARGET } from "@/datacenter/config/layout";
import { useInfrastructureStore } from "@/store/infrastructureStore";
import type { LinkStatus } from "@/types/infrastructure";

export const LINK_TARGET_NAME = "link-target";

const LINK_COLORS: Record<LinkStatus, string> = {
  connected: "#22d3ee",
  disconnecting: "#f59e0b",
  disconnected: "#ef4444",
  restoring: "#f59e0b",
};
const PULSE_COUNT = 6;
const PULSE_SPEED = 0.25;
const SPLIT_GAP = 0.35;

function tube(points: Vector3[]): TubeGeometry {
  return new TubeGeometry(new CatmullRomCurve3(points), 64, 0.035, 10, false);
}

export function ServiceLink() {
  const status = useInfrastructureStore((s) => s.link.status);
  const pulsesRef = useRef<Group>(null);

  const { curve, fullGeo, leftGeo, rightGeo, material } = useMemo(() => {
    const pts = LINK_POINTS.map((p) => new Vector3(...p));
    const mid = Math.floor(pts.length / 2);
    const left = pts.slice(0, mid + 1).map((p) => p.clone());
    const right = pts.slice(mid).map((p) => p.clone());
    left[left.length - 1].x -= SPLIT_GAP;
    left[left.length - 1].y = 0.05;
    right[0].x += SPLIT_GAP;
    right[0].y = 0.05;
    return {
      curve: new CatmullRomCurve3(pts),
      fullGeo: tube(pts),
      leftGeo: tube(left),
      rightGeo: tube(right),
      material: new MeshStandardMaterial({
        color: LINK_COLORS.connected,
        emissive: LINK_COLORS.connected,
        emissiveIntensity: 0.8,
        roughness: 0.4,
        metalness: 0.2,
      }),
    };
  }, []);

  useEffect(() => {
    material.color.set(LINK_COLORS[status]);
    material.emissive.set(LINK_COLORS[status]);
  }, [material, status]);

  useEffect(
    () => () => {
      fullGeo.dispose();
      leftGeo.dispose();
      rightGeo.dispose();
      material.dispose();
    },
    [fullGeo, leftGeo, rightGeo, material],
  );

  const connected = status === "connected";
  const pulsing = status === "disconnecting" || status === "restoring";

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    material.emissiveIntensity = pulsing ? 0.5 + Math.abs(Math.sin(t * 6)) : 0.8;
    const pulses = pulsesRef.current;
    if (!pulses) return;
    pulses.visible = connected;
    if (!connected) return;
    pulses.children.forEach((child, i) => {
      child.position.copy(curve.getPointAt((t * PULSE_SPEED + i / PULSE_COUNT) % 1));
    });
  });

  return (
    <group>
      <mesh geometry={fullGeo} material={material} visible={status !== "disconnected"} />
      <mesh geometry={leftGeo} material={material} visible={status === "disconnected"} />
      <mesh geometry={rightGeo} material={material} visible={status === "disconnected"} />

      <group ref={pulsesRef}>
        {Array.from({ length: PULSE_COUNT }, (_, i) => (
          <mesh key={i}>
            <sphereGeometry args={[0.055, 8, 8]} />
            <meshBasicMaterial color="#a5f3fc" toneMapped={false} />
          </mesh>
        ))}
      </group>

      {/* Floor service-bridge plate marking the maintenance zone */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 4.6]}>
        <planeGeometry args={[1.6, 1.0]} />
        <meshStandardMaterial color="#3b3f45" roughness={0.7} />
      </mesh>

      {/* Invisible raycast target. three.js raycasts invisible meshes, so visible={false} is fine. */}
      <mesh name={LINK_TARGET_NAME} position={LINK_TARGET.position} visible={false}>
        <boxGeometry args={LINK_TARGET.size} />
        <meshBasicMaterial />
      </mesh>
    </group>
  );
}
```

- [x] **Step 3: Write `NocWall.tsx`**

```tsx
import { Html } from "@react-three/drei";
import { NOC_WALL } from "@/datacenter/config/layout";
import { useAgentLogStore } from "@/store/agentLogStore";
import { useSceneStore } from "@/store/sceneStore";
import { useVoiceStore } from "@/store/voiceStore";

const AGENT_LABELS: Record<string, string> = {
  master: "Master Agent",
  diagnosis: "Diagnosis Agent",
  voice: "Voice Agent",
};

export function NocWall() {
  const phase = useSceneStore((s) => s.state);
  const activeAgent = useSceneStore((s) => s.activeAgent);
  const agentStatus = useSceneStore((s) => s.agentStatus);
  const entries = useAgentLogStore((s) => s.entries);
  const transcripts = useVoiceStore((s) => s.transcripts);
  const callActive = useVoiceStore((s) => s.callActive);

  return (
    <group position={NOC_WALL.position}>
      {/* Screen housing */}
      <mesh position={[0, 0, -0.06]}>
        <boxGeometry args={[NOC_WALL.width + 0.3, NOC_WALL.height + 0.3, 0.1]} />
        <meshStandardMaterial color="#0a0c0f" metalness={0.5} roughness={0.5} />
      </mesh>
      {/* drei transform mode: 1 CSS px = 0.025 world units × scale; 1000px × 0.025 × 0.4 = 10 m. */}
      <Html transform position={[0, 0, 0.001]} scale={NOC_WALL.htmlScale} zIndexRange={[5, 0]} pointerEvents="none">
        <div className={`dc-noc dc-noc--${phase.toLowerCase()}`}>
          <div className="dc-noc-header">
            <span>AI OPERATIONS CENTER</span>
            <span className="dc-noc-phase">{phase.replace("_", " ")}</span>
          </div>
          <div className="dc-noc-body">
            <section>
              <h3>ACTIVE AGENT</h3>
              <p className="dc-noc-big">{activeAgent ? AGENT_LABELS[activeAgent] ?? activeAgent : "—"}</p>
              <p className="dc-noc-sub">{agentStatus ?? ""}</p>
            </section>
            <section>
              <h3>EVENT FEED</h3>
              {entries.slice(-6).map((e) => (
                <p key={e.id} className={`dc-log dc-log--${e.level}`}>
                  {e.timestamp} {e.message}
                </p>
              ))}
            </section>
            <section>
              <h3>VOICE {callActive ? "· LIVE" : ""}</h3>
              {transcripts.slice(-3).map((t) => (
                <p key={t.id}>
                  <strong>{t.speaker === "agent" ? "AI" : "DBA"}:</strong> {t.text}
                </p>
              ))}
            </section>
          </div>
        </div>
      </Html>
    </group>
  );
}
```

- [x] **Step 4: Type-check and commit**

Run: `npx tsc --noEmit`
Expected: no errors

```bash
git add src/datacenter/scene/HeroRack.tsx src/datacenter/scene/ServiceLink.tsx src/datacenter/scene/NocWall.tsx
git commit -m "feat(datacenter): hero racks, ECS-Aurora service cable and NOC wall display"
```

---

## Task 11: Camera rig and hold-E interaction

**Files:**
- Create: `src_frontend/app/src/datacenter/lib/useKeyboard.ts`
- Create: `src_frontend/app/src/datacenter/scene/CameraRig.tsx`
- Create: `src_frontend/app/src/datacenter/scene/Interaction.tsx`

Key map:

| Key | Action |
|---|---|
| `↑`/`W`, `↓`/`S` | walk forward / back (walk mode) |
| `←`/`A`, `→`/`D` | turn left / right (walk mode) |
| `Shift` | sprint |
| `V` | toggle director / walk |
| `G` | switch to walk and jump to the service bridge stand point |
| `R` | return to spawn |
| hold `E` | disconnect link (walk mode, looking at bridge, ≤ 2.6 m) |

Nothing fires while an `<input>` or `<textarea>` has focus (DevPanel phone field).

- [x] **Step 1: Write `useKeyboard.ts`**

```ts
import { useEffect, useRef, type MutableRefObject } from "react";

const TRACKED = new Set([
  "arrowup", "arrowdown", "arrowleft", "arrowright",
  "w", "a", "s", "d", "shift",
]);

export function isTypingInField(): boolean {
  const el = document.activeElement;
  return el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
}

/** Set of currently held keys (lower-cased `KeyboardEvent.key`). Clears on window blur. */
export function useKeyboard(): MutableRefObject<Set<string>> {
  const keys = useRef(new Set<string>());

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (isTypingInField()) return;
      if (e.metaKey || e.ctrlKey) return;
      const k = e.key.toLowerCase();
      if (!TRACKED.has(k)) return;
      keys.current.add(k);
      if (k.startsWith("arrow")) e.preventDefault(); // stop page scroll
    };
    const up = (e: KeyboardEvent) => {
      keys.current.delete(e.key.toLowerCase());
    };
    const clear = () => keys.current.clear();

    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", clear);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", clear);
    };
  }, []);

  return keys;
}
```

- [x] **Step 2: Write `CameraRig.tsx`**

```tsx
import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { MathUtils, Vector3 } from "three";
import { LINK_STAND_POINT, PLAYER, RACK_BOXES, WALK_BOUNDS } from "@/datacenter/config/layout";
import { shotForPhase } from "@/datacenter/lib/cameraDirector";
import { resolveMove } from "@/datacenter/lib/collision";
import { isTypingInField, useKeyboard } from "@/datacenter/lib/useKeyboard";
import { useDataCenterUiStore } from "@/datacenter/store/dataCenterUiStore";
import { useSceneStore } from "@/store/sceneStore";

const WALK_SPEED = 2.2; // m/s
const SPRINT_MULT = 1.8;
const TURN_SPEED = 1.6; // rad/s
const DIRECTOR_DAMP = 2.5;
const MAX_STEP = 0.05;

const shotPos = new Vector3();
const shotTarget = new Vector3();

export function CameraRig() {
  const camera = useThree((s) => s.camera);
  const keys = useKeyboard();
  const mode = useDataCenterUiStore((s) => s.mode);

  const yaw = useRef<number>(PLAYER.spawnYaw);
  const pos = useRef(new Vector3(...PLAYER.spawn));
  const lookAt = useRef(new Vector3(0, 1, 0));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTypingInField() || e.repeat) return;
      const k = e.key.toLowerCase();
      const ui = useDataCenterUiStore.getState();
      if (k === "v") ui.toggleMode();
      if (k === "g") {
        ui.setMode("walk");
        pos.current.set(...LINK_STAND_POINT.position);
        yaw.current = LINK_STAND_POINT.yaw;
      }
      if (k === "r") {
        pos.current.set(...PLAYER.spawn);
        yaw.current = PLAYER.spawnYaw;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useFrame(({ clock }, dt) => {
    const step = Math.min(dt, MAX_STEP);

    if (mode === "director") {
      const shot = shotForPhase(useSceneStore.getState().state, clock.elapsedTime);
      shotPos.set(...shot.position);
      shotTarget.set(...shot.target);
      camera.position.x = MathUtils.damp(camera.position.x, shotPos.x, DIRECTOR_DAMP, step);
      camera.position.y = MathUtils.damp(camera.position.y, shotPos.y, DIRECTOR_DAMP, step);
      camera.position.z = MathUtils.damp(camera.position.z, shotPos.z, DIRECTOR_DAMP, step);
      lookAt.current.x = MathUtils.damp(lookAt.current.x, shotTarget.x, DIRECTOR_DAMP, step);
      lookAt.current.y = MathUtils.damp(lookAt.current.y, shotTarget.y, DIRECTOR_DAMP, step);
      lookAt.current.z = MathUtils.damp(lookAt.current.z, shotTarget.z, DIRECTOR_DAMP, step);
      camera.lookAt(lookAt.current);
      return;
    }

    const k = keys.current;
    const turn = (k.has("arrowleft") || k.has("a") ? 1 : 0) - (k.has("arrowright") || k.has("d") ? 1 : 0);
    const fwd = (k.has("arrowup") || k.has("w") ? 1 : 0) - (k.has("arrowdown") || k.has("s") ? 1 : 0);
    yaw.current += turn * TURN_SPEED * step;
    const dist = WALK_SPEED * (k.has("shift") ? SPRINT_MULT : 1) * fwd * step;
    // yaw 0 looks toward -z
    const dx = -Math.sin(yaw.current) * dist;
    const dz = -Math.cos(yaw.current) * dist;
    const next = resolveMove(pos.current.x, pos.current.z, dx, dz, RACK_BOXES, WALK_BOUNDS);
    pos.current.x = next.x;
    pos.current.z = next.z;

    camera.position.set(pos.current.x, PLAYER.eyeHeight, pos.current.z);
    camera.rotation.set(0, yaw.current, 0, "YXZ");
  });

  return null;
}
```

- [x] **Step 3: Write `Interaction.tsx`**

```tsx
import { useEffect } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Raycaster, Vector2 } from "three";
import { isTypingInField } from "@/datacenter/lib/useKeyboard";
import { LINK_TARGET_NAME } from "@/datacenter/scene/ServiceLink";
import { useDataCenterUiStore } from "@/datacenter/store/dataCenterUiStore";
import { canDisconnect, useInfrastructureStore } from "@/store/infrastructureStore";
import { useSceneStore } from "@/store/sceneStore";

const INTERACT_DISTANCE = 2.6;
const raycaster = new Raycaster();
const screenCenter = new Vector2(0, 0);

export function Interaction() {
  const camera = useThree((s) => s.camera);
  const scene = useThree((s) => s.scene);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.repeat || isTypingInField() || e.key.toLowerCase() !== "e") return;
      const ui = useDataCenterUiStore.getState();
      const infra = useInfrastructureStore.getState();
      const allowed = canDisconnect(useSceneStore.getState().state, infra.link, infra.pendingRequestId);
      if (ui.mode === "walk" && ui.lookingAtLink && allowed) ui.holdDispatch({ type: "press" });
    };
    const up = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "e") useDataCenterUiStore.getState().holdDispatch({ type: "release" });
    };
    const blur = () => useDataCenterUiStore.getState().holdDispatch({ type: "cancel" });
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  }, []);

  useFrame((_, dt) => {
    const ui = useDataCenterUiStore.getState();

    if (ui.mode === "walk") {
      raycaster.setFromCamera(screenCenter, camera);
      raycaster.far = INTERACT_DISTANCE;
      const target = scene.getObjectByName(LINK_TARGET_NAME);
      const looking = target ? raycaster.intersectObject(target, false).length > 0 : false;
      if (looking !== ui.lookingAtLink) ui.setLookingAtLink(looking);
      if (!looking && ui.hold.holding) ui.holdDispatch({ type: "cancel" });
    } else if (ui.lookingAtLink) {
      ui.setLookingAtLink(false);
    }

    if (ui.hold.holding) ui.holdDispatch({ type: "tick", dt: Math.min(dt, 0.05) });
  });

  return null;
}
```

The HUD's presenter button (Task 12) drives the same `holdDispatch`, so the tick loop here serves both director and walk mode.

- [x] **Step 4: Type-check and commit**

Run: `npx tsc --noEmit`
Expected: no errors

```bash
git add src/datacenter/lib/useKeyboard.ts src/datacenter/scene/CameraRig.tsx src/datacenter/scene/Interaction.tsx
git commit -m "feat(datacenter): director/walk camera rig and hold-E link interaction"
```

---

## Task 12: Scene composition, HUD, page and styles

**Files:**
- Create: `src_frontend/app/src/datacenter/scene/DataCenterScene.tsx`
- Create: `src_frontend/app/src/datacenter/hud/Hud.tsx`
- Create: `src_frontend/app/src/datacenter/datacenter.css`
- Modify: `src_frontend/app/src/datacenter/DataCenterPage.tsx` (replace the Task 5 placeholder)

- [x] **Step 1: Write `DataCenterScene.tsx`**

```tsx
import { HERO_RACKS } from "@/datacenter/config/layout";
import { CameraRig } from "@/datacenter/scene/CameraRig";
import { Facility } from "@/datacenter/scene/Facility";
import { HeroRack } from "@/datacenter/scene/HeroRack";
import { Interaction } from "@/datacenter/scene/Interaction";
import { NocWall } from "@/datacenter/scene/NocWall";
import { RackRows } from "@/datacenter/scene/RackRows";
import { ServiceLink } from "@/datacenter/scene/ServiceLink";

export function DataCenterScene() {
  return (
    <>
      <Facility />
      <RackRows />
      {HERO_RACKS.map((rack) => (
        <HeroRack key={rack.id} rack={rack} />
      ))}
      <ServiceLink />
      <NocWall />
      <CameraRig />
      <Interaction />
    </>
  );
}
```

- [x] **Step 2: Write `Hud.tsx`**

```tsx
import { AgentLog } from "@/components/AgentLog";
import { MetricsPanel } from "@/components/MetricsPanel";
import { useDataCenterUiStore } from "@/datacenter/store/dataCenterUiStore";
import { canDisconnect, useInfrastructureStore } from "@/store/infrastructureStore";
import { useSceneStore } from "@/store/sceneStore";
import { useVoiceStore } from "@/store/voiceStore";

const AGENT_LABELS: Record<string, string> = {
  master: "Master Agent",
  diagnosis: "Diagnosis Agent",
  voice: "Voice Agent",
};

export function Hud() {
  const phase = useSceneStore((s) => s.state);
  const connected = useSceneStore((s) => s.connected);
  const activeAgent = useSceneStore((s) => s.activeAgent);
  const reset = useSceneStore((s) => s.reset);

  const link = useInfrastructureStore((s) => s.link);
  const pendingRequestId = useInfrastructureStore((s) => s.pendingRequestId);
  const lastError = useInfrastructureStore((s) => s.lastError);
  const clearError = useInfrastructureStore((s) => s.clearError);

  const mode = useDataCenterUiStore((s) => s.mode);
  const toggleMode = useDataCenterUiStore((s) => s.toggleMode);
  const lookingAtLink = useDataCenterUiStore((s) => s.lookingAtLink);
  const hold = useDataCenterUiStore((s) => s.hold);
  const holdDispatch = useDataCenterUiStore((s) => s.holdDispatch);
  const panelOpen = useDataCenterUiStore((s) => s.panelOpen);
  const togglePanel = useDataCenterUiStore((s) => s.togglePanel);

  const transcripts = useVoiceStore((s) => s.transcripts);
  const callActive = useVoiceStore((s) => s.callActive);

  const allowed = canDisconnect(phase, link, pendingRequestId);
  const buttonAllowed = allowed && (mode === "director" || lookingAtLink);
  const progressPct = Math.round(hold.progress * 100);

  return (
    <div className="dc-hud">
      <header className="dc-topbar">
        <span className="dc-title">AI OPERATIONS CENTER · DATA CENTER TWIN</span>
        <span className={`dc-pill ${connected ? "dc-pill--ok" : "dc-pill--bad"}`}>{connected ? "WS LIVE" : "WS OFF"}</span>
        <span className={`dc-pill dc-pill--phase-${phase.toLowerCase()}`}>{phase.replace("_", " ")}</span>
        <span className="dc-pill">{activeAgent ? AGENT_LABELS[activeAgent] ?? activeAgent : "Agents idle"}</span>
        <span className={`dc-pill dc-pill--link-${link.status}`}>ECS→AURORA {link.status.toUpperCase()}</span>
      </header>

      {mode === "walk" && (
        <div className={`dc-reticle ${lookingAtLink ? "dc-reticle--active" : ""}`}>
          {lookingAtLink && (
            <div className="dc-prompt">
              <div>ECS → AURORA APPLICATION LINK · TCP/3306</div>
              <div>
                {allowed
                  ? "Hold E to disconnect — this triggers a real demo incident"
                  : phase === "HEALTHY"
                    ? "Link down — press RESET to restore the rule"
                    : "Link locked during incident"}
              </div>
              {hold.holding && <div className="dc-progress"><div style={{ width: `${progressPct}%` }} /></div>}
            </div>
          )}
        </div>
      )}

      <div className="dc-help">
        <span>V walk/director</span>
        <span>↑↓←→ move</span>
        <span>G go to link</span>
        <span>hold E disconnect</span>
        <span>R respawn</span>
        <span>Ctrl+D dev panel</span>
      </div>

      <aside className={`dc-panel ${panelOpen ? "" : "dc-panel--closed"}`}>
        <button className="dc-panel-toggle" onClick={togglePanel} aria-label="Toggle operations panel">
          {panelOpen ? "›" : "‹"}
        </button>
        {panelOpen && (
          <div className="dc-panel-body">
            <MetricsPanel />
            <AgentLog />
            <section className="sidebar-section">
              <h2>VOICE {callActive ? "· LIVE" : ""}</h2>
              {transcripts.slice(-4).map((t) => (
                <p key={t.id} className={`dc-transcript dc-transcript--${t.speaker}`}>
                  <strong>{t.speaker === "agent" ? "AI" : "DBA"}:</strong> {t.text}
                </p>
              ))}
            </section>
          </div>
        )}
      </aside>

      <footer className="dc-presenter">
        <button
          className={`dc-btn dc-btn--danger ${hold.holding ? "dc-btn--holding" : ""}`}
          disabled={!buttonAllowed}
          onPointerDown={(e) => {
            if (e.button !== 0 || !buttonAllowed) return;
            holdDispatch({ type: "press" });
          }}
          onPointerUp={() => holdDispatch({ type: "release" })}
          onPointerLeave={() => holdDispatch({ type: "release" })}
          onPointerCancel={() => holdDispatch({ type: "release" })}
          title={
            mode === "walk" && !lookingAtLink
              ? "In walk mode, face the service bridge (G) first"
              : "Hold for 1.25 s to remove the real security-group rule"
          }
        >
          {hold.holding ? `DISCONNECTING… ${progressPct}%` : "HOLD TO DISCONNECT LINK"}
        </button>
        <button className="dc-btn" onClick={reset} title="Stop incident, restore rule, return to HEALTHY">RESET</button>
        <button className="dc-btn" onClick={toggleMode}>{mode === "director" ? "WALK MODE" : "DIRECTOR MODE"}</button>
        <a className="dc-btn" href="/">CLASSIC UI</a>
      </footer>

      {lastError && (
        <div className="dc-toast" role="alert">
          <span>AWS operation failed: {lastError}</span>
          <button onClick={clearError} aria-label="Dismiss">✕</button>
        </div>
      )}
    </div>
  );
}
```

- [x] **Step 3: Replace `DataCenterPage.tsx`**

```tsx
import { Suspense, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { ACESFilmicToneMapping } from "three";
import { DevPanel } from "@/components/DevPanel";
import { Hud } from "@/datacenter/hud/Hud";
import { DataCenterScene } from "@/datacenter/scene/DataCenterScene";
import "@/styles/theme.css";
import "@/datacenter/datacenter.css";

function hasWebGl(): boolean {
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function DataCenterPage() {
  const supported = useMemo(hasWebGl, []);

  if (!supported) {
    return (
      <div className="dc-unsupported">
        <h1>3D view unavailable</h1>
        <p>This browser has no WebGL support.</p>
        <a href="/">Open the classic operations view</a>
      </div>
    );
  }

  return (
    <div className="dc-root">
      <Canvas
        dpr={[1, 1.5]}
        camera={{ fov: 60, near: 0.1, far: 120, position: [0, 3.8, 13] }}
        gl={{ antialias: true }}
        onCreated={({ gl }) => {
          gl.toneMapping = ACESFilmicToneMapping;
        }}
      >
        <Suspense fallback={null}>
          <DataCenterScene />
        </Suspense>
      </Canvas>
      <Hud />
      <DevPanel />
    </div>
  );
}
```

- [x] **Step 4: Write `datacenter.css`**

```css
/* Scope everything to .dc-root so the classic UI is untouched. */
.dc-root {
  position: fixed;
  inset: 0;
  background: #07090c;
  font-family: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
  color: #d7dde5;
}
.dc-root canvas { display: block; }
.dc-root * { font-family: inherit; }

.dc-hud { position: absolute; inset: 0; pointer-events: none; z-index: 20; }
.dc-hud button, .dc-hud a, .dc-hud aside { pointer-events: auto; }

/* Top bar */
.dc-topbar {
  position: absolute; top: 0; left: 0; right: 0;
  display: flex; gap: 10px; align-items: center;
  padding: 10px 16px;
  background: linear-gradient(rgba(7, 9, 12, 0.92), rgba(7, 9, 12, 0));
  font-size: 12px; letter-spacing: 0.06em;
}
.dc-title { font-weight: 600; margin-right: auto; color: #f1f5f9; }
.dc-pill { padding: 3px 10px; border: 1px solid #2b323b; border-radius: 3px; background: rgba(15, 18, 23, 0.85); }
.dc-pill--ok { border-color: #16a34a; color: #4ade80; }
.dc-pill--bad { border-color: #dc2626; color: #f87171; }
.dc-pill--phase-healthy { color: #4ade80; }
.dc-pill--phase-incident_detected, .dc-pill--phase-diagnosing, .dc-pill--phase-calling { color: #f87171; border-color: #7f1d1d; }
.dc-pill--phase-recovering { color: #fbbf24; border-color: #78350f; }
.dc-pill--phase-resolved { color: #4ade80; border-color: #14532d; }
.dc-pill--link-connected { color: #67e8f9; }
.dc-pill--link-disconnecting, .dc-pill--link-restoring { color: #fbbf24; }
.dc-pill--link-disconnected { color: #f87171; }

/* Reticle and prompt */
.dc-reticle {
  position: absolute; left: 50%; top: 50%;
  width: 6px; height: 6px; margin: -3px 0 0 -3px;
  border-radius: 50%; background: rgba(255, 255, 255, 0.6);
}
.dc-reticle--active { background: #22d3ee; box-shadow: 0 0 12px #22d3ee; }
.dc-prompt {
  position: absolute; top: 24px; left: 50%; transform: translateX(-50%);
  min-width: 360px; padding: 10px 14px;
  background: rgba(10, 12, 16, 0.9); border: 1px solid #22d3ee;
  font-size: 12px; line-height: 1.6; text-align: center; white-space: nowrap;
}
.dc-progress { height: 4px; margin-top: 8px; background: #1f2937; }
.dc-progress > div { height: 100%; background: #f59e0b; transition: width 60ms linear; }

/* Help strip */
.dc-help {
  position: absolute; left: 16px; bottom: 64px;
  display: flex; flex-direction: column; gap: 2px;
  font-size: 11px; color: #94a3b8; opacity: 0.85;
}

/* Right operations panel (reuses .sidebar-section styles from theme.css) */
.dc-panel {
  position: absolute; top: 48px; right: 0; bottom: 60px;
  width: 340px; display: flex;
  background: rgba(10, 12, 16, 0.88); border-left: 1px solid #1f2937;
}
.dc-panel--closed { width: 0; background: transparent; border: none; }
.dc-panel-toggle {
  position: absolute; left: -26px; top: 8px;
  width: 26px; height: 40px; border: 1px solid #1f2937; border-right: none;
  background: rgba(10, 12, 16, 0.88); color: #d7dde5; cursor: pointer; font-size: 18px;
}
.dc-panel-body { flex: 1; overflow-y: auto; padding: 12px 16px; font-size: 12px; }
.dc-panel-body .sidebar-section h2 { font-size: 11px; letter-spacing: 0.08em; }
.dc-transcript { margin: 4px 0; line-height: 1.4; }
.dc-transcript--human { color: #93c5fd; }

/* Presenter row */
.dc-presenter {
  position: absolute; left: 0; right: 0; bottom: 0;
  display: flex; gap: 8px; justify-content: center; padding: 12px;
  background: linear-gradient(rgba(7, 9, 12, 0), rgba(7, 9, 12, 0.92));
}
.dc-btn {
  padding: 8px 14px; font-size: 12px; letter-spacing: 0.06em; text-decoration: none;
  color: #e2e8f0; background: #111827; border: 1px solid #334155; border-radius: 3px; cursor: pointer;
}
.dc-btn:hover:not(:disabled) { border-color: #64748b; }
.dc-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.dc-btn--danger { border-color: #7f1d1d; color: #fca5a5; }
.dc-btn--holding { background: #7f1d1d; color: #fff; }

/* Error toast */
.dc-toast {
  position: absolute; top: 56px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 12px; align-items: center; padding: 10px 14px;
  background: #3f0d0d; border: 1px solid #dc2626; color: #fecaca; font-size: 12px;
}
.dc-toast button { background: none; border: none; color: inherit; cursor: pointer; }

/* Unsupported browser */
.dc-unsupported { padding: 48px; color: #e2e8f0; font-family: ui-monospace, monospace; }
.dc-unsupported a { color: #67e8f9; }

/* In-scene rack labels (drei Html, non-transform) */
.dc-rack-label {
  padding: 6px 10px; border: 1px solid #334155; border-radius: 3px;
  background: rgba(10, 12, 16, 0.85); color: #e2e8f0;
  font-size: 12px; line-height: 1.5; white-space: nowrap; text-align: center;
}
.dc-rack-title { font-weight: 600; letter-spacing: 0.06em; }
.dc-rack-metrics { color: #94a3b8; }
.dc-rack-status { font-size: 10px; letter-spacing: 0.1em; color: #4ade80; }
.dc-rack-label--alert { border-color: #dc2626; }
.dc-rack-label--alert .dc-rack-status { color: #f87171; }
.dc-rack-label--recovering { border-color: #f59e0b; }
.dc-rack-label--recovering .dc-rack-status { color: #fbbf24; }

/* NOC wall (drei Html transform; sized in CSS px, scaled to metres in NocWall.tsx) */
.dc-noc {
  width: 1000px; height: 300px; box-sizing: border-box; padding: 18px 24px;
  background: #0b1118; color: #cbd5e1; border: 2px solid #1e293b;
  font-size: 16px; line-height: 1.5; display: flex; flex-direction: column; gap: 12px;
}
.dc-noc-header { display: flex; justify-content: space-between; font-size: 20px; font-weight: 600; letter-spacing: 0.1em; color: #f1f5f9; }
.dc-noc-phase { color: #4ade80; }
.dc-noc--incident_detected .dc-noc-phase, .dc-noc--diagnosing .dc-noc-phase, .dc-noc--calling .dc-noc-phase { color: #f87171; }
.dc-noc--recovering .dc-noc-phase { color: #fbbf24; }
.dc-noc-body { display: grid; grid-template-columns: 1fr 1.6fr 1.2fr; gap: 20px; flex: 1; min-height: 0; }
.dc-noc-body section { overflow: hidden; }
.dc-noc-body h3 { margin: 0 0 6px; font-size: 12px; letter-spacing: 0.12em; color: #64748b; }
.dc-noc-body p { margin: 0 0 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dc-noc-big { font-size: 22px; color: #f1f5f9; }
.dc-noc-sub { color: #94a3b8; }
.dc-log--warn { color: #fbbf24; }
.dc-log--error { color: #f87171; }
.dc-log--success { color: #4ade80; }
```

- [x] **Step 5: Type-check, test, build**

```bash
npx tsc --noEmit
npm test -- --run
npm run build
```
Expected: no type errors, 26 tests pass, build succeeds.

Confirm Three.js is not in the classic bundle:

```bash
grep -l "WebGLRenderer" dist/assets/*.js
```
Expected: only the `DataCenterPage-*.js` chunk (or a `three-*` vendor chunk it imports), never `index-*.js`.

- [x] **Step 6: Commit**

```bash
git add src/datacenter
git commit -m "feat(datacenter): scene composition, operations HUD, page shell and styles"
```

---

## Task 13: End-to-end verification against the real backend

No code in this task unless something breaks. Run the backend locally the way you normally do (see `docs/backend/`), then `npm run dev` in `src_frontend/app`.

- [x] **Step 1: Classic UI regression**

Open `http://localhost:3000/`. City renders, sidebar metrics tick, Ctrl+D opens DevPanel, "Break DB" still works and the incident loop completes. Nothing here may have changed.

- [x] **Step 2: Director mode idle**

Open `http://localhost:3000/datacenter`. Expect: slow orbit over four rack rows, LEDs blinking, cyan cable with moving pulses between the ECS and Aurora racks, rack labels showing live CPU/MEM/IOPS, network rack showing `ALLOW ECS_SG → RDS_SG TCP/3306`, NOC wall readable from the orbit. Top bar shows `WS LIVE`, `HEALTHY`, `ECS→AURORA CONNECTED`.

- [x] **Step 3: Walk mode and interaction**

Press `V`, then arrows to walk; confirm you cannot walk into racks or through walls. Press `R` to respawn. Press `G`: the camera jumps to the bridge stand point facing it; the reticle turns cyan and the prompt appears. Hold `E` for 1.25 s: prompt shows progress, cable turns amber (`disconnecting`), then red and split (`disconnected`), network rack shows `RULE MISSING`, alarm strobe starts, top bar phase goes to `INCIDENT DETECTED`. Release early once to confirm cancel works and nothing is sent (check backend log).

- [ ] **Step 4: Director mode through the incident** — partially verified locally (2026-09-15): the `DIAGNOSING` fly-in to the Aurora rack and the wide pull-back on `RESOLVED` are confirmed. The `CALLING` NOC-wall move with transcript lines and the `RECOVERING` amber→cyan cable are **deferred to Step 8**: locally the Twilio call fails instantly (no phone number), so `CALLING` lasts ~150 ms and `_apply_network_fix` never runs.

Press `V` back to director. Camera flies to the Aurora rack during `DIAGNOSING`, to the NOC wall during `CALLING` (transcript lines appear on the wall and in the right panel), to the bridge during `RECOVERING` where the cable turns amber then cyan and pulses resume, then pulls back wide on `RESOLVED`.

- [x] **Step 5: Presenter shortcut**

From `HEALTHY`, press and hold the `HOLD TO DISCONNECT LINK` button for 1.25 s with the mouse. Same sequence as Step 3 without walking. Releasing early must not send.

- [x] **Step 6: Reset and sync**

Click `RESET` mid-incident: cable goes amber then cyan, phase returns to `HEALTHY`. Refresh `/datacenter` mid-incident in a second tab: cable is already red, phase correct, presenter button disabled (hydrated from `system_status`). Break from the classic tab's DevPanel: the 3D tab's cable reacts.

- [ ] **Step 7: Failure path** — partially verified locally (2026-09-15). With a bogus `RDS_SECURITY_GROUP_ID` the boot pre-check fails (`restore_db_access result=error`), the link comes up `disconnected`, the presenter button is `disabled`, and a full hold sends nothing (no revoke, no incident, real SG untouched) — so **"no incident starts" is confirmed**. The amber-flash→cyan rollback and red toast are **not reachable this way**: boot and revoke use the same SG pair, so a bogus id disables the button before any request is sent. Reaching them needs a genuine runtime AWS failure (denied permission / lost connectivity); no read-only profile exists for this account. Currently covered only by `infrastructureStore.test.ts` rollback tests.

Temporarily point `RDS_SECURITY_GROUP_ID` at a non-existent group, restart the backend, hold to disconnect: cable flashes amber then returns cyan, red toast shows the AWS error, no incident starts. Restore the env var.

- [x] **Step 8: Deploy** — deployed 2026-09-15. Deep link `https://<cf>/datacenter` returns 200 via the SPA fallback and renders at native resolution (3456×1748), `WS LIVE`, no console errors. Steps 2–3 re-verified on the deployed stack. Step 4 re-run with a real call: `CALLING` lasted ~90 s, NOC-wall event feed grew with call/RCA lines, and the voice agent's `apply_network_fix` genuinely restored the SG rule. Still **not** observed: the `RECOVERING` cable amber→cyan in a tab held open through the call (it stayed red until reload; backend state was correct), and the camera move to the NOC wall during `CALLING`. Fixed en route: `aws_sdk_bedrock_runtime` pin (commit `0d669fc`). Booth note: rack/NOC label text is too small at native resolution (caveat 5, `distanceFactor` untuned).

Rebuild the frontend first (the CloudFront bucket only gets what `dist/` contains), then deploy both stacks:

```bash
cd src_frontend/app && npm run build && cd ../..
cdk deploy RcaBackendStack-dev01 RcaFrontendStack-dev01
```

Open `https://<cloudfront-domain>/datacenter` directly (deep link must work via the existing 403/404 → `index.html` fallback) and repeat Steps 2–4 once on the booth laptop at its native resolution.

- [x] **Step 9: Commit any fixes and add a README line**

Add under the demo/usage section of `README.md`:

```markdown
- **3D data-center view:** open `/datacenter`. `V` toggles walk mode, `G` jumps to the service link, hold `E` (or the HUD button) to disconnect it. The classic view stays at `/`.
```

```bash
git add README.md
git commit -m "docs: mention /datacenter 3D view"
```

---

## Acceptance criteria

- Existing UI at `/` is byte-for-byte unchanged in behaviour and does not download Three.js.
- `/datacenter` loads in under 5 s on the venue network after cache miss (no external assets beyond the JS chunks).
- Cable visuals only change on backend `infrastructure_link_update`; a failed AWS call leaves the cable connected and shows the error.
- A second `break_database` during `disconnecting` is ignored by the backend.
- Refresh or second client shows correct link and phase state.
- Reset and voice-agent remediation both reconnect the cable.
- Keyboard-only operation is sufficient: `G` then hold `E` completes the break without a mouse.
- Backend suite and frontend suite both green.

## Deferred (only if asked for after the booth run)

- Mouse look / pointer lock in walk mode.
- Canvas-texture NOC wall instead of DOM overlay.
- Baked shadows or post-processing.
- Sound design.
- Additional links (e.g. API Gateway → ECS) reusing the same `infrastructure_link_update` contract with a different `link_id`.
