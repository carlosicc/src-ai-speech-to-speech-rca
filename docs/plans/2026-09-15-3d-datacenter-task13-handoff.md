# Handoff: 3D data-center UI — Task 13 (end-to-end verification)

> **Status:** Tasks 1–12 done and committed on `feat/3d-datacenter-ui` (21 commits, HEAD `3fb2ca5`, nothing merged into `main`).
> Task 13 is the only remaining work; it needs the real backend + AWS and the user runs it interactively.
> Plan of record: `docs/plans/2026-09-14-3d-datacenter-ui.md` (Task 13 steps at lines ~2578–2632).

## What exists now

- New route `/datacenter` (lazy chunk). Route `*` still renders the classic `<App />`; `/` is unchanged and never downloads three.js.
- Backend owns an authoritative `LinkStatus` (`connected | disconnecting | disconnected | restoring`) in `src_backend/shared/state.py`, mirroring the real RDS security-group ingress rule (TCP/3306 from the ECS SG). `error` is a transient broadcast event, never a stored state.
- New WebSocket message `infrastructure_link_update`; additive `infrastructure_links` array inside `system_status`. Contract documented in `docs/frontend/api-contract.md` ("Infrastructure Link State").
- `break_database` from the 3D UI carries `{request_id, source: "datacenter_3d", link_id}`; the backend ignores a second request while `disconnecting`.
- Frontend never guesses link state: the store applies only backend updates, with rollback `disconnecting → connected` and `restoring → disconnected` on `error`.
- Scene: instanced rack rows (52 racks / 416 LEDs), tube cable with pulses, drei `Html` labels and NOC wall, two camera modes (director cinematic per phase; walk = yaw-only first person with AABB slide collision). No physics engine.
- Interaction: hold `E` for 1.25 s while looking at the service bridge, or hold the HUD button. `V` toggles mode, `G` snaps to the bridge stand point, `R` respawns.

## Verification already done (2026-09-14)

| Check | Result |
|---|---|
| Backend unit tests | 215 passed, 2 pre-existing failures (see below) |
| Frontend vitest | 26 passed |
| `npx tsc --noEmit` | clean |
| `npm run build` | ok; `index-*.js` 209 kB, `DataCenterPage-*.js` 846 kB (230 kB gzip); `WebGLRenderer` only in the lazy chunk |
| Browser smoke test | `/datacenter` renders, HUD + walk mode work; `/` unchanged |

## How to run things

```bash
# backend tests (.venv/bin/pytest has a stale shebang from the old project path — use python -m)
.venv/bin/python -m pytest tests/unit -q          # ~4 min, CDK tests dominate

# frontend
cd src_frontend/app && npm test -- --run
cd src_frontend/app && npx tsc --noEmit
cd src_frontend/app && npm run dev                # http://localhost:3000/datacenter
```

Two backend failures are pre-existing on the base commit `a9e89b2` and unrelated to this feature (verified in a throwaway worktree):
`tests/unit/test_phase4_ux_fixes.py::TestIssue3_TwilioCallingTimeout::test_twilio_calling_timeout_config` (expects 45, code has 90) and
`tests/unit/test_phase6.py::TestMasterAgentTools::test_update_incident_status_recovering` (CALLING != RECOVERING).

## Known caveats to expect during Task 13

1. **Startup sync is pessimistic.** `sync_link_status_from_aws()` runs in `lifespan()` and marks the link `disconnected` when the SG ids are blank or AWS is unreachable. On a laptop without credentials the 3D cable starts red and the presenter button starts disabled. This also changes what Step 7 (failure path) looks like: with a bogus `RDS_SECURITY_GROUP_ID` the link is already `disconnected` at boot, so the amber-flash-then-cyan rollback only shows if startup sync succeeded first.
2. **Timed-out voice call.** If the call times out after the rule was removed, the demo can sit at phase `HEALTHY` with link `disconnected`. Recovery is the `RESET` button.
3. **`_apply_network_fix` still reports success on restore failure** (`src_backend/voice/voice_tools.py`): it broadcasts `error` + `disconnected`, but the phase-advance block below still returns success and advances the phase. Pre-existing shape of that function; left untouched deliberately.
4. **`requestDisconnect()` does not check socket state** — if the WebSocket is down the click is a no-op with no toast.
5. **Walk camera has no pitch** (yaw only, by design) and **lighting plus drei `distanceFactor` label sizes are untuned**; expect cosmetic tweaking at the booth resolution.
6. **Deploy needs a fresh build.** CloudFront serves whatever is in `dist/`, so always `npm run build` before `cdk deploy RcaBackendStack-dev01 RcaFrontendStack-dev01`.

## Task 13 remaining steps

1. Classic UI regression at `/`.
2. Director mode idle at `/datacenter`.
3. Walk mode and interaction (hold `E`, and release early to confirm nothing is sent).
4. Director mode through the full incident.
5. Presenter shortcut (HUD hold button).
6. Reset and cross-tab sync / refresh hydration.
7. Failure path with a bogus security-group id (see caveat 1).
8. Rebuild frontend, deploy both `-dev01` stacks, retest the deep link at native booth resolution.
9. Commit any fixes and add the `/datacenter` line to `README.md` (exact wording in the plan).

Do not merge `feat/3d-datacenter-ui` without being asked.
