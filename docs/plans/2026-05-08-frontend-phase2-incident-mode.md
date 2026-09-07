# Phase 2: Incident Mode — Implementation Plan

> **Status: COMPLETED** (2026-05-08)

**Goal:** When an incident triggers, the affected room reacts visually (flashes red, characters panic), other rooms dim, and a Dev Panel (Ctrl+D) lets booth operators control the demo.

**Architecture:** The CityScene renderer gains room-specific visual effects driven by the Zustand store's `state` + `affectedService`. A new `RoomEffects` module computes per-room overlays/tints per frame. A `DevPanel` React component toggles with Ctrl+D and provides trigger/advance/reset buttons.

**Tech Stack:** Canvas 2D (existing), Zustand (existing), React 18, TypeScript

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/engine/effects.ts` (create) | Pure functions: compute room overlay color/alpha and character behavior per state+room |
| `src/engine/CityScene.ts` (modify) | Apply room overlays, pass affectedRoom to character update logic |
| `src/store/sceneStore.ts` (modify) | Add auto-advance timer, expose subscribe for CityScene |
| `src/components/DevPanel.tsx` (create) | Ctrl+D toggled overlay with trigger/advance/reset buttons |
| `src/app/App.tsx` (modify) | Mount DevPanel |
| `src/styles/theme.css` (modify) | DevPanel styling |

---

### Task 1: Room Effects Module

**Files:**
- Create: `src_frontend/app/src/engine/effects.ts`

This module is pure functions — no DOM, no Canvas, no side effects. It computes what overlays to apply per room based on current state.

- [ ] **Step 1: Create the effects module with overlay computation**

```typescript
// src_frontend/app/src/engine/effects.ts
import type { SceneState } from "@/types/scene";

export interface RoomOverlay {
  color: string;
  alpha: number;
}

export function getRoomOverlay(
  roomId: string,
  affectedRoom: string | null,
  state: SceneState,
  time: number
): RoomOverlay | null {
  const isAffected = roomId === affectedRoom;

  switch (state) {
    case "HEALTHY":
    case "RESOLVED":
      return null;

    case "INCIDENT_DETECTED":
      if (isAffected) {
        // Flash red — oscillates between 0.15 and 0.35 alpha
        const flash = 0.25 + Math.sin(time * 0.15) * 0.1;
        return { color: "#ff0000", alpha: flash };
      }
      // Other rooms dim slightly
      return { color: "#000000", alpha: 0.15 };

    case "DIAGNOSING":
      if (isAffected) {
        // Pulse orange
        const pulse = 0.2 + Math.sin(time * 0.1) * 0.08;
        return { color: "#ff6600", alpha: pulse };
      }
      return null;

    case "CALLING":
      if (isAffected) {
        return { color: "#ff0000", alpha: 0.2 };
      }
      return null;

    case "RECOVERING":
      if (isAffected) {
        // Flicker — rapidly alternating alpha
        const flicker = Math.random() > 0.7 ? 0.12 : 0;
        return { color: "#ff0000", alpha: flicker };
      }
      return null;
  }
}

export type CharBehavior = "walk" | "idle" | "panic";

export function getCharacterBehavior(
  charRoom: string,
  affectedRoom: string | null,
  state: SceneState
): CharBehavior {
  const isInAffected = charRoom === affectedRoom;

  switch (state) {
    case "HEALTHY":
    case "RESOLVED":
      return "walk";
    case "INCIDENT_DETECTED":
      return isInAffected ? "panic" : "idle";
    case "DIAGNOSING":
      return isInAffected ? "panic" : "idle";
    case "CALLING":
    case "RECOVERING":
      return "idle";
  }
}
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src_frontend/app/src/engine/effects.ts
git commit -m "feat(frontend): add room effects module for incident mode overlays"
```

---

### Task 2: Apply Room Overlays in CityScene

**Files:**
- Modify: `src_frontend/app/src/engine/CityScene.ts`

The `drawBuilding()` method needs to draw a colored overlay rectangle on top of each room when an effect is active. The scene needs to know the current `affectedService` and `state`.

- [ ] **Step 1: Add state tracking properties and import effects**

Add to the top of `CityScene.ts`:

```typescript
import { getRoomOverlay, getCharacterBehavior } from "@/engine/effects";
```

Add private fields after the existing ones (after line 44):

```typescript
  private currentState: SceneState = "HEALTHY";
  private affectedRoom: string | null = null;
```

- [ ] **Step 2: Update transitionTo to store state and affectedRoom**

Replace the existing `transitionTo` method (lines 354-371):

```typescript
  transitionTo(state: SceneState, affectedRoom: string | null = null): void {
    this.currentState = state;
    this.affectedRoom = affectedRoom;
  }
```

- [ ] **Step 3: Draw room overlays in drawBuilding**

After the existing room border/floor/furniture/label drawing (after line 264, before the closing `}` of the for-loop), add:

```typescript
      // Room effect overlay
      const overlay = getRoomOverlay(room.id, this.affectedRoom, this.currentState, this.time);
      if (overlay) {
        ctx.fillStyle = overlay.color;
        ctx.globalAlpha = overlay.alpha;
        ctx.fillRect(rx, ry, room.width, ROOM_HEIGHT);
        ctx.globalAlpha = 1;
      }
```

- [ ] **Step 4: Update character behavior per room**

Replace the `updateCharacters` method (lines 267-297) to use room-aware behavior:

```typescript
  private updateCharacters(): void {
    for (const ch of this.characters) {
      const roomCfg = ROOMS[ch.room];
      const behavior = getCharacterBehavior(roomCfg.id, this.affectedRoom, this.currentState);
      ch.animState = behavior;

      ch.frameTimer++;
      const speed = ch.animState === "panic" ? 4 : 10;
      if (ch.frameTimer >= speed) {
        ch.frameTimer = 0;
        ch.frame = (ch.frame + 1) % 4;
      }

      if (ch.animState === "idle") {
        ch.waitTimer = 10;
        continue;
      }

      if (ch.waitTimer > 0) {
        ch.waitTimer--;
        continue;
      }

      const dx = ch.tx - ch.x;

      if (Math.abs(dx) < 1) {
        ch.waitTimer = ch.animState === "panic" ? 10 + Math.random() * 20 : 40 + Math.random() * 80;
        ch.tx = roomCfg.x + 10 + Math.random() * (roomCfg.width - 20);
      } else {
        const moveSpeed = ch.animState === "panic" ? ch.speed * 2.5 : ch.speed;
        ch.x += Math.sign(dx) * moveSpeed;
        ch.facingLeft = dx < 0;
      }
    }
  }
```

- [ ] **Step 5: Update CityCanvas.tsx to pass affectedRoom**

In `src_frontend/app/src/components/CityCanvas.tsx`, update the second `useEffect`:

```typescript
  const affectedService = useSceneStore((s) => s.affectedService);

  useEffect(() => {
    sceneRef.current?.transitionTo(sceneState, affectedService);
  }, [sceneState, affectedService]);
```

- [ ] **Step 6: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add src_frontend/app/src/engine/CityScene.ts src_frontend/app/src/components/CityCanvas.tsx
git commit -m "feat(frontend): apply room-specific overlays and character behavior during incidents"
```

---

### Task 3: Dev Panel Component

**Files:**
- Create: `src_frontend/app/src/components/DevPanel.tsx`
- Modify: `src_frontend/app/src/app/App.tsx`
- Modify: `src_frontend/app/src/styles/theme.css`

A floating panel toggled with Ctrl+D. Shows current state, buttons to trigger incident on each room, advance phase, and reset.

- [ ] **Step 1: Create DevPanel component**

```typescript
// src_frontend/app/src/components/DevPanel.tsx
import { useState, useEffect } from "react";
import { useSceneStore } from "@/store/sceneStore";
import { ROOMS } from "@/engine/config";

export function DevPanel() {
  const [visible, setVisible] = useState(false);
  const state = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);
  const triggerIncident = useSceneStore((s) => s.triggerIncident);
  const advancePhase = useSceneStore((s) => s.advancePhase);
  const reset = useSceneStore((s) => s.reset);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "d") {
        e.preventDefault();
        setVisible((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (!visible) return null;

  return (
    <div className="dev-panel">
      <div className="dev-panel-header">
        <span>DEV PANEL</span>
        <button onClick={() => setVisible(false)}>✕</button>
      </div>
      <div className="dev-panel-state">
        State: <strong>{state}</strong>
        {affectedService && <> | Room: <strong>{affectedService}</strong></>}
      </div>
      <div className="dev-panel-section">
        <label>TRIGGER INCIDENT:</label>
        <div className="dev-panel-buttons">
          {ROOMS.map((r) => (
            <button
              key={r.id}
              onClick={() => triggerIncident(r.id)}
              disabled={state !== "HEALTHY"}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="dev-panel-section">
        <label>CONTROL:</label>
        <div className="dev-panel-buttons">
          <button onClick={advancePhase}>Advance Phase →</button>
          <button onClick={reset}>Reset</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add DevPanel styles to theme.css**

Append to `src_frontend/app/src/styles/theme.css`:

```css
/* Dev Panel (Ctrl+D) */
.dev-panel {
  position: fixed;
  bottom: 16px;
  left: 16px;
  background: rgba(15, 20, 41, 0.95);
  border: 1px solid #26c6da;
  border-radius: 8px;
  padding: 16px;
  z-index: 9999;
  font-size: 12px;
  min-width: 280px;
  max-width: 360px;
}

.dev-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  color: var(--accent-cyan);
  font-weight: bold;
  letter-spacing: 1px;
}

.dev-panel-header button {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
}

.dev-panel-state {
  margin-bottom: 12px;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
  color: var(--text-primary);
}

.dev-panel-section {
  margin-bottom: 10px;
}

.dev-panel-section label {
  display: block;
  font-size: 10px;
  letter-spacing: 1px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.dev-panel-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.dev-panel-buttons button {
  background: rgba(38, 198, 218, 0.1);
  border: 1px solid rgba(38, 198, 218, 0.3);
  color: var(--text-primary);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  font-family: var(--font-mono);
}

.dev-panel-buttons button:hover {
  background: rgba(38, 198, 218, 0.2);
  border-color: var(--accent-cyan);
}

.dev-panel-buttons button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

- [ ] **Step 3: Mount DevPanel in App.tsx**

Update `src_frontend/app/src/app/App.tsx`:

```typescript
import { CityCanvas } from "@/components/CityCanvas";
import { Sidebar } from "@/components/Sidebar";
import { DevPanel } from "@/components/DevPanel";
import "@/styles/theme.css";

export function App() {
  return (
    <div className="app-layout">
      <CityCanvas />
      <Sidebar />
      <DevPanel />
    </div>
  );
}
```

- [ ] **Step 4: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add src_frontend/app/src/components/DevPanel.tsx src_frontend/app/src/styles/theme.css src_frontend/app/src/app/App.tsx
git commit -m "feat(frontend): add Dev Panel (Ctrl+D) for incident trigger and state control"
```

---

### Task 4: Auto-Advance Timer for Demo Loop

**Files:**
- Modify: `src_frontend/app/src/store/sceneStore.ts`

When an incident is triggered, the state machine auto-advances through phases on a timer (simulating the demo loop without backend). Each phase lasts a few seconds.

- [ ] **Step 1: Add auto-advance to the store**

Replace `src_frontend/app/src/store/sceneStore.ts`:

```typescript
import { create } from "zustand";
import type { SceneState } from "@/types/scene";

interface SceneStore {
  state: SceneState;
  affectedService: string | null;
  autoAdvance: boolean;
  triggerIncident: (service: string) => void;
  advancePhase: () => void;
  reset: () => void;
  setAutoAdvance: (enabled: boolean) => void;
}

const STATE_ORDER: SceneState[] = [
  "HEALTHY",
  "INCIDENT_DETECTED",
  "DIAGNOSING",
  "CALLING",
  "RECOVERING",
  "RESOLVED",
];

const PHASE_DURATIONS: Record<SceneState, number> = {
  HEALTHY: 0,
  INCIDENT_DETECTED: 3000,
  DIAGNOSING: 4000,
  CALLING: 5000,
  RECOVERING: 3000,
  RESOLVED: 2000,
};

let autoTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleNext(get: () => SceneStore) {
  if (autoTimer) clearTimeout(autoTimer);
  const { state, autoAdvance } = get();
  if (!autoAdvance || state === "HEALTHY") return;

  const duration = PHASE_DURATIONS[state];
  if (duration <= 0) return;

  autoTimer = setTimeout(() => {
    const store = get();
    if (store.autoAdvance) {
      store.advancePhase();
    }
  }, duration);
}

export const useSceneStore = create<SceneStore>((set, get) => ({
  state: "HEALTHY",
  affectedService: null,
  autoAdvance: true,
  triggerIncident: (service: string) => {
    set({ state: "INCIDENT_DETECTED", affectedService: service });
    scheduleNext(get);
  },
  advancePhase: () => {
    const current = STATE_ORDER.indexOf(get().state);
    const next = STATE_ORDER[(current + 1) % STATE_ORDER.length];
    set({
      state: next,
      affectedService: next === "HEALTHY" ? null : get().affectedService,
    });
    scheduleNext(get);
  },
  reset: () => {
    if (autoTimer) clearTimeout(autoTimer);
    set({ state: "HEALTHY", affectedService: null });
  },
  setAutoAdvance: (enabled: boolean) => {
    set({ autoAdvance: enabled });
    if (enabled) scheduleNext(get);
    else if (autoTimer) clearTimeout(autoTimer);
  },
}));
```

- [ ] **Step 2: Add auto-advance toggle to DevPanel**

In `src_frontend/app/src/components/DevPanel.tsx`, add after the existing store selectors:

```typescript
  const autoAdvance = useSceneStore((s) => s.autoAdvance);
  const setAutoAdvance = useSceneStore((s) => s.setAutoAdvance);
```

Add a toggle in the CONTROL section (after the Reset button):

```typescript
          <button onClick={() => setAutoAdvance(!autoAdvance)}>
            Auto: {autoAdvance ? "ON" : "OFF"}
          </button>
```

- [ ] **Step 3: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src_frontend/app/src/store/sceneStore.ts src_frontend/app/src/components/DevPanel.tsx
git commit -m "feat(frontend): add auto-advance timer for demo loop state progression"
```

---

### Task 5: Visual Polish — Sidebar Reacts to State

**Files:**
- Modify: `src_frontend/app/src/components/Sidebar.tsx`
- Modify: `src_frontend/app/src/styles/theme.css`

The sidebar should show more expressive state: pulsing red dot for affected service, agent status messages per phase, and a subtle animation when active.

- [ ] **Step 1: Enhance Sidebar with state-specific messaging**

Replace `src_frontend/app/src/components/Sidebar.tsx`:

```typescript
import { useSceneStore } from "@/store/sceneStore";
import { ROOMS } from "@/engine/config";
import type { SceneState } from "@/types/scene";

const AGENT_MESSAGES: Record<SceneState, string> = {
  HEALTHY: "Monitoring system activity. No issues detected.",
  INCIDENT_DETECTED: "⚠ ALERT — Anomaly detected. Activating diagnosis protocol...",
  DIAGNOSING: "Running health checks, pulling logs, analyzing root cause...",
  CALLING: "Escalating to on-call DBA. Initiating voice call...",
  RECOVERING: "Recovery procedure in progress. Monitoring restoration...",
  RESOLVED: "✓ Incident resolved. All systems nominal.",
};

export function Sidebar() {
  const state = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);

  const isActive = state !== "HEALTHY";

  return (
    <div className="sidebar">
      <h1 className="sidebar-title">AI OPERATIONS CENTER</h1>

      <section className="sidebar-section">
        <h2>SYSTEMS OVERVIEW</h2>
        <ul className="system-list">
          {ROOMS.map((r) => {
            const isAffected = affectedService === r.id;
            return (
              <li key={r.id} className={`system-item${isAffected ? " system-item--alert" : ""}`}>
                <span
                  className={`status-dot${isAffected ? " status-dot--alert" : ""}`}
                  style={{
                    backgroundColor: isAffected ? "#ef5350" : "#4caf50",
                  }}
                />
                <span className="system-label">{r.label}</span>
                <span className="system-status">
                  {isAffected ? "ALERT" : "HEALTHY"}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="sidebar-section">
        <h2>AI AGENT STATUS</h2>
        <div className="agent-status">
          <span className={`agent-indicator${isActive ? " agent-indicator--active" : ""}`} />
          <span>{isActive ? state.replace("_", " ") : "Idle"}</span>
        </div>
        <p className="agent-message">{AGENT_MESSAGES[state]}</p>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Add alert animations to theme.css**

Append to `src_frontend/app/src/styles/theme.css`:

```css
/* Alert states */
.status-dot--alert {
  animation: pulse-red 1s infinite;
}

@keyframes pulse-red {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px #ef5350; }
  50% { opacity: 0.5; box-shadow: 0 0 8px #ef5350; }
}

.system-item--alert .system-status {
  color: var(--accent-red);
  font-weight: bold;
}

.agent-indicator--active {
  background: var(--accent-red);
  animation: pulse-fast 0.8s infinite;
}

@keyframes pulse-fast {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
```

- [ ] **Step 3: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src_frontend/app/src/components/Sidebar.tsx src_frontend/app/src/styles/theme.css
git commit -m "feat(frontend): enhance sidebar with state-specific agent messages and alert animations"
```

---

### Task 6: Integration Test — Full Demo Loop

**Files:**
- Verify visually in browser

This task is manual verification. Start the dev server, open the app, use Ctrl+D to trigger an incident, and verify the full loop.

- [ ] **Step 1: Start dev server**

Run: `cd src_frontend/app && npm run dev`

- [ ] **Step 2: Verify in browser**

Open http://localhost:3000. Check:
1. Building renders with rooms and characters walking normally
2. Press Ctrl+D — Dev Panel appears
3. Click "Aurora DB (Server Room)" to trigger incident
4. Verify: Aurora DB room flashes red, its character panics, other characters idle
5. Verify: Sidebar shows Aurora DB as "ALERT" with pulsing red dot
6. Verify: State auto-advances through DIAGNOSING → CALLING → RECOVERING → RESOLVED → HEALTHY
7. Verify: Each state shows different overlay (orange pulse, static red, flicker, none)
8. Verify: After RESOLVED, everything returns to normal
9. Click Reset — verify immediate return to HEALTHY

- [ ] **Step 3: Fix any issues found**

If compilation or visual issues are found, fix them before final commit.

- [ ] **Step 4: Final commit if fixes were needed**

```bash
git add -u
git commit -m "fix(frontend): address issues found during phase 2 integration test"
```
