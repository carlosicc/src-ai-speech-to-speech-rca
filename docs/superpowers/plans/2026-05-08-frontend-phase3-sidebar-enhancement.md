# Phase 3: Right Sidebar Enhancement — Implementation Plan

> **Status: COMPLETED** (2026-05-08)

**Goal:** Add live sparkline metrics (CPU/MEM/IOPS per service) and a timestamped AI Agent Log to the sidebar, both reacting to scene state changes.

**Architecture:** A new Zustand metrics store generates mock data on an interval timer. Metrics fluctuate normally during HEALTHY, spike/drop for the affected service during incidents, and restore on RESOLVED. The Agent Log store accumulates timestamped entries pushed by the sceneStore on each state transition. Two new components (`MetricsPanel`, `AgentLog`) render in the sidebar.

**Tech Stack:** Canvas 2D sparklines (tiny inline canvases), Zustand, React 18, TypeScript

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/store/metricsStore.ts` (create) | Zustand store: per-service metric values, tick timer, state-reactive fluctuation |
| `src/store/agentLogStore.ts` (create) | Zustand store: array of timestamped log entries, push/clear actions |
| `src/components/MetricsPanel.tsx` (create) | Renders sparkline bars for each service's CPU/MEM/IOPS |
| `src/components/AgentLog.tsx` (create) | Scrollable list of timestamped agent reasoning entries |
| `src/components/Sidebar.tsx` (modify) | Compose MetricsPanel and AgentLog into the sidebar |
| `src/store/sceneStore.ts` (modify) | Push log entries on state transitions |
| `src/styles/theme.css` (modify) | Styles for metrics and log components |

---

### Task 1: Metrics Store

**Files:**
- Create: `src_frontend/app/src/store/metricsStore.ts`

- [ ] **Step 1: Create the metrics store**

```typescript
// src_frontend/app/src/store/metricsStore.ts
import { create } from "zustand";
import type { SceneState } from "@/types/scene";

export interface ServiceMetrics {
  cpu: number[];
  mem: number[];
  iops: number[];
}

interface MetricsStore {
  metrics: Record<string, ServiceMetrics>;
  start: (serviceIds: string[]) => void;
  stop: () => void;
  tick: (state: SceneState, affectedService: string | null) => void;
}

const HISTORY_LENGTH = 20;

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

function fluctuate(current: number, base: number, variance: number): number {
  const drift = (Math.random() - 0.5) * variance;
  const pull = (base - current) * 0.1;
  return clamp(current + drift + pull, 0, 100);
}

function spike(current: number): number {
  return clamp(current + (Math.random() * 15 + 10), 0, 100);
}

function drop(current: number): number {
  return clamp(current - (Math.random() * 10 + 5), 0, 100);
}

let intervalId: ReturnType<typeof setInterval> | null = null;

export const useMetricsStore = create<MetricsStore>((set, get) => ({
  metrics: {},

  start: (serviceIds: string[]) => {
    const initial: Record<string, ServiceMetrics> = {};
    for (const id of serviceIds) {
      initial[id] = {
        cpu: Array(HISTORY_LENGTH).fill(30 + Math.random() * 20),
        mem: Array(HISTORY_LENGTH).fill(40 + Math.random() * 15),
        iops: Array(HISTORY_LENGTH).fill(20 + Math.random() * 10),
      };
    }
    set({ metrics: initial });
  },

  stop: () => {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
  },

  tick: (state: SceneState, affectedService: string | null) => {
    set((prev) => {
      const next: Record<string, ServiceMetrics> = {};
      for (const [id, m] of Object.entries(prev.metrics)) {
        const isAffected = id === affectedService;
        const isIncident = state !== "HEALTHY" && state !== "RESOLVED";

        let cpu: number, mem: number, iops: number;
        const lastCpu = m.cpu[m.cpu.length - 1];
        const lastMem = m.mem[m.mem.length - 1];
        const lastIops = m.iops[m.iops.length - 1];

        if (isAffected && isIncident) {
          cpu = spike(lastCpu);
          mem = spike(lastMem);
          iops = drop(lastIops);
        } else {
          cpu = fluctuate(lastCpu, 35, 6);
          mem = fluctuate(lastMem, 45, 4);
          iops = fluctuate(lastIops, 25, 5);
        }

        next[id] = {
          cpu: [...m.cpu.slice(1), cpu],
          mem: [...m.mem.slice(1), mem],
          iops: [...m.iops.slice(1), iops],
        };
      }
      return { metrics: next };
    });
  },
}));
```

- [ ] **Step 2: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src_frontend/app/src/store/metricsStore.ts
git commit -m "feat(frontend): add metrics store with mock fluctuation and incident spikes"
```

---

### Task 2: Agent Log Store

**Files:**
- Create: `src_frontend/app/src/store/agentLogStore.ts`

- [ ] **Step 1: Create the agent log store**

```typescript
// src_frontend/app/src/store/agentLogStore.ts
import { create } from "zustand";

export interface LogEntry {
  id: number;
  timestamp: string;
  message: string;
  level: "info" | "warn" | "error" | "success";
}

interface AgentLogStore {
  entries: LogEntry[];
  push: (message: string, level?: LogEntry["level"]) => void;
  clear: () => void;
}

let nextId = 1;

export const useAgentLogStore = create<AgentLogStore>((set) => ({
  entries: [],

  push: (message: string, level: LogEntry["level"] = "info") => {
    const entry: LogEntry = {
      id: nextId++,
      timestamp: new Date().toLocaleTimeString("en-GB", { hour12: false }),
      message,
      level,
    };
    set((prev) => ({
      entries: [...prev.entries.slice(-49), entry],
    }));
  },

  clear: () => {
    set({ entries: [] });
  },
}));
```

- [ ] **Step 2: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src_frontend/app/src/store/agentLogStore.ts
git commit -m "feat(frontend): add agent log store with timestamped entries"
```

---

### Task 3: Wire Scene Store to Push Log Entries

**Files:**
- Modify: `src_frontend/app/src/store/sceneStore.ts`

On each state transition (`triggerIncident`, `advancePhase`), push a descriptive log entry to the agent log store. Also on `reset`, clear the log.

- [ ] **Step 1: Add log pushes to sceneStore**

Add import at the top of `sceneStore.ts`:

```typescript
import { useAgentLogStore } from "@/store/agentLogStore";
```

Modify `triggerIncident` — after the existing `set(...)` call and before `scheduleNext(get)`, add:

```typescript
    useAgentLogStore.getState().push(
      `Incident detected on ${service}. Activating response protocol.`,
      "error"
    );
```

Modify `advancePhase` — after the existing `set(...)` call and before `scheduleNext(get)`, add a log message based on the new state:

```typescript
    const LOG_MESSAGES: Partial<Record<SceneState, { msg: string; level: LogEntry["level"] }>> = {
      DIAGNOSING: { msg: "Diagnosis agent activated. Pulling logs and running health checks...", level: "warn" },
      CALLING: { msg: "Escalation triggered. Connecting to on-call DBA via voice...", level: "warn" },
      RECOVERING: { msg: "DBA confirmed. Executing recovery procedure...", level: "info" },
      RESOLVED: { msg: "All systems restored. Incident resolved successfully.", level: "success" },
      HEALTHY: { msg: "System nominal. Returning to monitoring state.", level: "info" },
    };
    const logEntry = LOG_MESSAGES[next];
    if (logEntry) {
      useAgentLogStore.getState().push(logEntry.msg, logEntry.level);
    }
```

Add the `LogEntry` type import:

```typescript
import type { LogEntry } from "@/store/agentLogStore";
```

Modify `reset` — after clearing the timer and setting state, add:

```typescript
    useAgentLogStore.getState().clear();
```

- [ ] **Step 2: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src_frontend/app/src/store/sceneStore.ts
git commit -m "feat(frontend): push agent log entries on state transitions"
```

---

### Task 4: Metrics Panel Component

**Files:**
- Create: `src_frontend/app/src/components/MetricsPanel.tsx`

Renders a compact sparkline bar per service. Each service shows 3 tiny bars (CPU, MEM, IOPS) drawn on inline canvas elements.

- [ ] **Step 1: Create the MetricsPanel component**

```typescript
// src_frontend/app/src/components/MetricsPanel.tsx
import { useEffect, useRef } from "react";
import { useMetricsStore } from "@/store/metricsStore";
import { useSceneStore } from "@/store/sceneStore";
import { ROOMS } from "@/engine/config";

const BAR_WIDTH = 3;
const BAR_GAP = 1;
const SPARK_HEIGHT = 20;
const SPARK_WIDTH = (BAR_WIDTH + BAR_GAP) * 20;

function Sparkline({ data, color }: { data: number[]; color: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, SPARK_WIDTH, SPARK_HEIGHT);

    for (let i = 0; i < data.length; i++) {
      const h = (data[i] / 100) * SPARK_HEIGHT;
      ctx.fillStyle = data[i] > 80 ? "#ef5350" : color;
      ctx.fillRect(i * (BAR_WIDTH + BAR_GAP), SPARK_HEIGHT - h, BAR_WIDTH, h);
    }
  }, [data, color]);

  return (
    <canvas
      ref={canvasRef}
      width={SPARK_WIDTH}
      height={SPARK_HEIGHT}
      className="sparkline-canvas"
    />
  );
}

export function MetricsPanel() {
  const metrics = useMetricsStore((s) => s.metrics);
  const start = useMetricsStore((s) => s.start);
  const tick = useMetricsStore((s) => s.tick);
  const sceneState = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);

  useEffect(() => {
    start(ROOMS.map((r) => r.id));
  }, [start]);

  useEffect(() => {
    const id = setInterval(() => {
      tick(sceneState, affectedService);
    }, 800);
    return () => clearInterval(id);
  }, [tick, sceneState, affectedService]);

  return (
    <section className="sidebar-section">
      <h2>LIVE METRICS</h2>
      <div className="metrics-grid">
        {ROOMS.slice(0, 4).map((room) => {
          const m = metrics[room.id];
          if (!m) return null;
          return (
            <div key={room.id} className="metrics-service">
              <span className="metrics-label">{room.id}</span>
              <div className="metrics-bars">
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">CPU</span>
                  <Sparkline data={m.cpu} color="#26c6da" />
                  <span className="metrics-bar-value">{Math.round(m.cpu[m.cpu.length - 1])}%</span>
                </div>
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">MEM</span>
                  <Sparkline data={m.mem} color="#7c4dff" />
                  <span className="metrics-bar-value">{Math.round(m.mem[m.mem.length - 1])}%</span>
                </div>
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">IOPS</span>
                  <Sparkline data={m.iops} color="#4caf50" />
                  <span className="metrics-bar-value">{Math.round(m.iops[m.iops.length - 1])}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src_frontend/app/src/components/MetricsPanel.tsx
git commit -m "feat(frontend): add MetricsPanel with sparkline bars for service metrics"
```

---

### Task 5: Agent Log Component

**Files:**
- Create: `src_frontend/app/src/components/AgentLog.tsx`

A scrollable log of timestamped agent reasoning entries. Auto-scrolls to bottom on new entries.

- [ ] **Step 1: Create the AgentLog component**

```typescript
// src_frontend/app/src/components/AgentLog.tsx
import { useEffect, useRef } from "react";
import { useAgentLogStore } from "@/store/agentLogStore";

const LEVEL_COLORS: Record<string, string> = {
  info: "#9e9e9e",
  warn: "#ffa726",
  error: "#ef5350",
  success: "#4caf50",
};

export function AgentLog() {
  const entries = useAgentLogStore((s) => s.entries);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries]);

  return (
    <section className="sidebar-section">
      <h2>AI AGENT LOG</h2>
      <div className="agent-log" ref={scrollRef}>
        {entries.length === 0 && (
          <p className="agent-log-empty">No activity yet.</p>
        )}
        {entries.map((e) => (
          <div key={e.id} className="agent-log-entry">
            <span className="agent-log-time">{e.timestamp}</span>
            <span
              className="agent-log-msg"
              style={{ color: LEVEL_COLORS[e.level] }}
            >
              {e.message}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src_frontend/app/src/components/AgentLog.tsx
git commit -m "feat(frontend): add AgentLog component with auto-scroll"
```

---

### Task 6: Compose Sidebar + Styles

**Files:**
- Modify: `src_frontend/app/src/components/Sidebar.tsx`
- Modify: `src_frontend/app/src/styles/theme.css`

Mount MetricsPanel and AgentLog inside the Sidebar, and add CSS for both.

- [ ] **Step 1: Update Sidebar to include new components**

Replace `src_frontend/app/src/components/Sidebar.tsx`:

```typescript
import { useSceneStore } from "@/store/sceneStore";
import { ROOMS } from "@/engine/config";
import type { SceneState } from "@/types/scene";
import { MetricsPanel } from "@/components/MetricsPanel";
import { AgentLog } from "@/components/AgentLog";

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

      <MetricsPanel />

      <section className="sidebar-section">
        <h2>AI AGENT STATUS</h2>
        <div className="agent-status">
          <span className={`agent-indicator${isActive ? " agent-indicator--active" : ""}`} />
          <span>{isActive ? state.replace("_", " ") : "Idle"}</span>
        </div>
        <p className="agent-message">{AGENT_MESSAGES[state]}</p>
      </section>

      <AgentLog />
    </div>
  );
}
```

- [ ] **Step 2: Append metrics and log styles to theme.css**

Append at the end of `src_frontend/app/src/styles/theme.css`:

```css
/* Metrics Panel */
.metrics-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.metrics-service {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metrics-label {
  font-size: 10px;
  color: var(--accent-cyan);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.metrics-bars {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.metrics-bar-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.metrics-bar-label {
  font-size: 9px;
  color: var(--text-secondary);
  width: 28px;
  flex-shrink: 0;
}

.sparkline-canvas {
  image-rendering: pixelated;
  height: 16px;
  flex: 1;
}

.metrics-bar-value {
  font-size: 10px;
  color: var(--text-primary);
  width: 30px;
  text-align: right;
}

/* Agent Log */
.agent-log {
  max-height: 160px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}

.agent-log-empty {
  font-size: 11px;
  color: var(--text-secondary);
  font-style: italic;
}

.agent-log-entry {
  display: flex;
  gap: 8px;
  font-size: 11px;
  line-height: 1.4;
}

.agent-log-time {
  color: var(--text-secondary);
  flex-shrink: 0;
  font-size: 10px;
}

.agent-log-msg {
  word-break: break-word;
}
```

- [ ] **Step 3: Verify compilation**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src_frontend/app/src/components/Sidebar.tsx src_frontend/app/src/styles/theme.css
git commit -m "feat(frontend): compose MetricsPanel and AgentLog into sidebar with styles"
```

---

### Task 7: Integration Test — Full Demo Loop

**Files:**
- Verify visually in browser

- [ ] **Step 1: Start dev server**

Run: `cd src_frontend/app && npm run dev`

- [ ] **Step 2: Verify in browser**

Open the app. Check:
1. Sidebar shows Systems Overview, Metrics, Agent Status, and Agent Log sections
2. Sparkline bars animate with mock fluctuation in HEALTHY state
3. Press Ctrl+D → trigger incident on "aurora-db"
4. Verify: Aurora DB metrics spike (CPU/MEM go red), IOPS drops
5. Verify: Agent Log shows timestamped entries appearing per phase
6. Verify: Log auto-scrolls as new entries appear
7. Verify: After RESOLVED → HEALTHY, metrics return to normal fluctuation
8. Click Reset in dev panel → verify log clears

- [ ] **Step 3: Fix any issues found**

- [ ] **Step 4: Final commit if fixes were needed**

```bash
git add -u
git commit -m "fix(frontend): address issues found during phase 3 integration test"
```
