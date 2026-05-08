# Frontend Animated City — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a PixiJS animated pixel-art city with buildings, data-flow connection lines, and walking characters inside the existing Vite+React app.

**Architecture:** PixiJS v8 runs in a `<div>` managed by a ref-based React wrapper (`CityCanvas`). A Zustand store holds scene state (`HEALTHY` initially). The PixiJS `CityScene` class orchestrates layers (background, buildings, connections, characters, effects). A basic sidebar shell shows placeholder system info. Placeholder colored-rectangle sprites are used until real art assets arrive.

**Tech Stack:** React 18, PixiJS 8, Zustand, Vite 5, TypeScript strict

---

## File Structure

```
src_frontend/app/
├── package.json              (modify — add pixi.js, zustand)
├── src/
│   ├── app/
│   │   └── App.tsx           (modify — layout with CityCanvas + Sidebar)
│   ├── components/
│   │   ├── CityCanvas.tsx    (create — React wrapper for PixiJS)
│   │   └── Sidebar.tsx       (create — right panel shell)
│   ├── engine/
│   │   ├── CityScene.ts      (create — orchestrates PixiJS app + layers)
│   │   ├── config.ts         (create — positions, paths, timing)
│   │   └── layers/
│   │       ├── BackgroundLayer.ts  (create)
│   │       ├── BuildingLayer.ts    (create)
│   │       ├── ConnectionLayer.ts  (create)
│   │       └── CharacterLayer.ts   (create)
│   ├── store/
│   │   └── sceneStore.ts     (create — Zustand state machine)
│   ├── types/
│   │   └── scene.ts          (create — SceneState, BuildingConfig, etc.)
│   └── styles/
│       └── theme.css         (create — dark theme, layout)
├── public/
│   └── sprites/              (create — placeholder PNGs generated at build time)
```

---

### Task 1: Add Dependencies

**Files:**
- Modify: `src_frontend/app/package.json`

- [ ] **Step 1: Add pixi.js and zustand to dependencies**

In `package.json`, add to `"dependencies"`:
```json
"pixi.js": "^8.4.0",
"zustand": "^5.0.0"
```

- [ ] **Step 2: Install**

Run: `cd src_frontend/app && npm install`
Expected: `node_modules/pixi.js` and `node_modules/zustand` exist, no errors.

- [ ] **Step 3: Commit**

```bash
git add src_frontend/app/package.json src_frontend/app/package-lock.json
git commit -m "feat(frontend): add pixi.js and zustand dependencies"
```

---

### Task 2: Types & Store

**Files:**
- Create: `src/types/scene.ts`
- Create: `src/store/sceneStore.ts`

- [ ] **Step 1: Create scene types**

Create `src/types/scene.ts`:
```typescript
export type SceneState =
  | "HEALTHY"
  | "INCIDENT_DETECTED"
  | "DIAGNOSING"
  | "CALLING"
  | "RECOVERING"
  | "RESOLVED";

export interface BuildingConfig {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  color: number;
}

export interface ConnectionConfig {
  from: string;
  to: string;
}

export interface CharacterConfig {
  id: string;
  color: number;
  path: { x: number; y: number }[];
  speed: number;
}
```

- [ ] **Step 2: Create Zustand store**

Create `src/store/sceneStore.ts`:
```typescript
import { create } from "zustand";
import type { SceneState } from "@/types/scene";

interface SceneStore {
  state: SceneState;
  affectedService: string | null;
  triggerIncident: (service: string) => void;
  advancePhase: () => void;
  reset: () => void;
}

const STATE_ORDER: SceneState[] = [
  "HEALTHY",
  "INCIDENT_DETECTED",
  "DIAGNOSING",
  "CALLING",
  "RECOVERING",
  "RESOLVED",
];

export const useSceneStore = create<SceneStore>((set, get) => ({
  state: "HEALTHY",
  affectedService: null,
  triggerIncident: (service: string) =>
    set({ state: "INCIDENT_DETECTED", affectedService: service }),
  advancePhase: () => {
    const current = STATE_ORDER.indexOf(get().state);
    const next = STATE_ORDER[(current + 1) % STATE_ORDER.length];
    set({
      state: next,
      affectedService: next === "HEALTHY" ? null : get().affectedService,
    });
  },
  reset: () => set({ state: "HEALTHY", affectedService: null }),
}));
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/types/scene.ts src/store/sceneStore.ts
git commit -m "feat(frontend): add scene types and Zustand store"
```

---

### Task 3: Engine Config

**Files:**
- Create: `src/engine/config.ts`

- [ ] **Step 1: Create config with building positions, connections, and character paths**

Create `src/engine/config.ts`:
```typescript
import type { BuildingConfig, ConnectionConfig, CharacterConfig } from "@/types/scene";

export const CANVAS_WIDTH = 1920;
export const CANVAS_HEIGHT = 1080;

export const BUILDINGS: BuildingConfig[] = [
  { id: "aurora-db", label: "Aurora DB", x: 300, y: 350, width: 128, height: 128, color: 0x4fc3f7 },
  { id: "api-gateway", label: "API Gateway", x: 600, y: 300, width: 128, height: 128, color: 0x81c784 },
  { id: "network", label: "Network", x: 900, y: 320, width: 128, height: 96, color: 0xffb74d },
  { id: "ecs-cluster", label: "ECS Cluster", x: 250, y: 650, width: 128, height: 128, color: 0xce93d8 },
  { id: "lambda", label: "Lambda Functions", x: 550, y: 680, width: 96, height: 96, color: 0xfff176 },
  { id: "s3-storage", label: "S3 Storage", x: 800, y: 700, width: 96, height: 96, color: 0xef5350 },
  { id: "monitoring", label: "Monitoring", x: 1050, y: 670, width: 96, height: 96, color: 0x26c6da },
];

export const CONNECTIONS: ConnectionConfig[] = [
  { from: "api-gateway", to: "aurora-db" },
  { from: "api-gateway", to: "ecs-cluster" },
  { from: "api-gateway", to: "lambda" },
  { from: "ecs-cluster", to: "aurora-db" },
  { from: "lambda", to: "s3-storage" },
  { from: "monitoring", to: "ecs-cluster" },
  { from: "monitoring", to: "lambda" },
  { from: "network", to: "api-gateway" },
];

export const CHARACTERS: CharacterConfig[] = [
  {
    id: "engineer-1",
    color: 0x42a5f5,
    speed: 1.2,
    path: [
      { x: 350, y: 520 },
      { x: 600, y: 470 },
      { x: 900, y: 460 },
      { x: 600, y: 470 },
    ],
  },
  {
    id: "engineer-2",
    color: 0x66bb6a,
    speed: 0.9,
    path: [
      { x: 280, y: 800 },
      { x: 550, y: 810 },
      { x: 820, y: 830 },
      { x: 550, y: 810 },
    ],
  },
  {
    id: "engineer-3",
    color: 0xffa726,
    speed: 1.0,
    path: [
      { x: 1050, y: 800 },
      { x: 800, y: 830 },
      { x: 550, y: 810 },
      { x: 800, y: 830 },
    ],
  },
];
```

- [ ] **Step 2: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/engine/config.ts
git commit -m "feat(frontend): add city scene configuration (buildings, connections, characters)"
```

---

### Task 4: Background Layer

**Files:**
- Create: `src/engine/layers/BackgroundLayer.ts`

- [ ] **Step 1: Implement BackgroundLayer**

Create `src/engine/layers/BackgroundLayer.ts`:
```typescript
import { Container, Graphics } from "pixi.js";
import { CANVAS_WIDTH, CANVAS_HEIGHT } from "@/engine/config";

export class BackgroundLayer {
  readonly container = new Container();

  constructor() {
    this.container.label = "background";
    this.draw();
  }

  private draw(): void {
    const g = new Graphics();
    // Dark sky gradient (approximated with two rects)
    g.rect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT * 0.4).fill(0x0a0e1a);
    g.rect(0, CANVAS_HEIGHT * 0.4, CANVAS_WIDTH, CANVAS_HEIGHT * 0.6).fill(0x0d1225);
    // Ground line
    g.rect(0, CANVAS_HEIGHT * 0.85, CANVAS_WIDTH, 2).fill(0x1a2744);
    // A few "stars"
    for (let i = 0; i < 60; i++) {
      const sx = Math.random() * CANVAS_WIDTH;
      const sy = Math.random() * CANVAS_HEIGHT * 0.35;
      g.circle(sx, sy, Math.random() * 1.5 + 0.5).fill(0xffffff);
    }
    this.container.addChild(g);
  }

  destroy(): void {
    this.container.destroy({ children: true });
  }
}
```

- [ ] **Step 2: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/engine/layers/BackgroundLayer.ts
git commit -m "feat(frontend): add BackgroundLayer with dark city sky"
```

---

### Task 5: Building Layer

**Files:**
- Create: `src/engine/layers/BuildingLayer.ts`

- [ ] **Step 1: Implement BuildingLayer**

Create `src/engine/layers/BuildingLayer.ts`:
```typescript
import { Container, Graphics, Text, TextStyle } from "pixi.js";
import { BUILDINGS } from "@/engine/config";
import type { BuildingConfig } from "@/types/scene";

export class BuildingLayer {
  readonly container = new Container();
  private buildings = new Map<string, Graphics>();
  private glowPhase = 0;

  constructor() {
    this.container.label = "buildings";
    this.draw();
  }

  private draw(): void {
    for (const cfg of BUILDINGS) {
      const g = new Graphics();
      g.roundRect(0, 0, cfg.width, cfg.height, 6).fill(cfg.color);
      g.position.set(cfg.x, cfg.y);
      g.alpha = 0.85;
      this.buildings.set(cfg.id, g);
      this.container.addChild(g);

      const label = new Text({
        text: cfg.label,
        style: new TextStyle({
          fontFamily: "monospace",
          fontSize: 13,
          fill: 0xffffff,
          align: "center",
        }),
      });
      label.anchor.set(0.5, 0);
      label.position.set(cfg.x + cfg.width / 2, cfg.y + cfg.height + 6);
      this.container.addChild(label);
    }
  }

  update(dt: number): void {
    this.glowPhase += dt * 0.02;
    const pulse = 0.8 + Math.sin(this.glowPhase) * 0.1;
    for (const g of this.buildings.values()) {
      g.alpha = pulse;
    }
  }

  getBuilding(id: string): Graphics | undefined {
    return this.buildings.get(id);
  }

  getBuildingCenter(id: string): { x: number; y: number } | null {
    const cfg = BUILDINGS.find((b) => b.id === id);
    if (!cfg) return null;
    return { x: cfg.x + cfg.width / 2, y: cfg.y + cfg.height / 2 };
  }

  destroy(): void {
    this.container.destroy({ children: true });
  }
}
```

- [ ] **Step 2: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/engine/layers/BuildingLayer.ts
git commit -m "feat(frontend): add BuildingLayer with labeled building sprites"
```

---

### Task 6: Connection Layer

**Files:**
- Create: `src/engine/layers/ConnectionLayer.ts`

- [ ] **Step 1: Implement ConnectionLayer with flowing particles**

Create `src/engine/layers/ConnectionLayer.ts`:
```typescript
import { Container, Graphics } from "pixi.js";
import { CONNECTIONS, BUILDINGS } from "@/engine/config";

interface Particle {
  x: number;
  y: number;
  progress: number;
  speed: number;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
}

export class ConnectionLayer {
  readonly container = new Container();
  private lines = new Graphics();
  private particleGraphics = new Graphics();
  private particles: Particle[] = [];

  constructor() {
    this.container.label = "connections";
    this.container.addChild(this.lines);
    this.container.addChild(this.particleGraphics);
    this.drawLines();
    this.initParticles();
  }

  private getCenter(id: string): { x: number; y: number } {
    const b = BUILDINGS.find((b) => b.id === id)!;
    return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  }

  private drawLines(): void {
    this.lines.clear();
    for (const conn of CONNECTIONS) {
      const from = this.getCenter(conn.from);
      const to = this.getCenter(conn.to);
      this.lines.moveTo(from.x, from.y).lineTo(to.x, to.y).stroke({ width: 1.5, color: 0x1b5e20, alpha: 0.4 });
    }
  }

  private initParticles(): void {
    for (const conn of CONNECTIONS) {
      const from = this.getCenter(conn.from);
      const to = this.getCenter(conn.to);
      for (let i = 0; i < 3; i++) {
        this.particles.push({
          x: from.x,
          y: from.y,
          progress: i / 3,
          speed: 0.003 + Math.random() * 0.002,
          fromX: from.x,
          fromY: from.y,
          toX: to.x,
          toY: to.y,
        });
      }
    }
  }

  update(dt: number): void {
    this.particleGraphics.clear();
    for (const p of this.particles) {
      p.progress += p.speed * dt;
      if (p.progress > 1) p.progress -= 1;
      p.x = p.fromX + (p.toX - p.fromX) * p.progress;
      p.y = p.fromY + (p.toY - p.fromY) * p.progress;
      this.particleGraphics.circle(p.x, p.y, 3).fill({ color: 0x4caf50, alpha: 0.8 });
    }
  }

  destroy(): void {
    this.container.destroy({ children: true });
  }
}
```

- [ ] **Step 2: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/engine/layers/ConnectionLayer.ts
git commit -m "feat(frontend): add ConnectionLayer with flowing data particles"
```

---

### Task 7: Character Layer

**Files:**
- Create: `src/engine/layers/CharacterLayer.ts`

- [ ] **Step 1: Implement CharacterLayer with walking characters**

Create `src/engine/layers/CharacterLayer.ts`:
```typescript
import { Container, Graphics } from "pixi.js";
import { CHARACTERS } from "@/engine/config";
import type { CharacterConfig } from "@/types/scene";

interface CharacterState {
  config: CharacterConfig;
  x: number;
  y: number;
  targetIndex: number;
  waitTimer: number;
  graphic: Graphics;
}

export class CharacterLayer {
  readonly container = new Container();
  private characters: CharacterState[] = [];

  constructor() {
    this.container.label = "characters";
    this.init();
  }

  private init(): void {
    for (const cfg of CHARACTERS) {
      const g = new Graphics();
      // Simple character: body rect + head circle
      g.circle(0, -16, 8).fill(cfg.color);
      g.roundRect(-6, -8, 12, 20, 3).fill(cfg.color);
      this.container.addChild(g);

      const start = cfg.path[0];
      g.position.set(start.x, start.y);

      this.characters.push({
        config: cfg,
        x: start.x,
        y: start.y,
        targetIndex: 1,
        waitTimer: 0,
        graphic: g,
      });
    }
  }

  update(dt: number): void {
    for (const ch of this.characters) {
      if (ch.waitTimer > 0) {
        ch.waitTimer -= dt;
        // Idle bob
        ch.graphic.position.y = ch.y + Math.sin(Date.now() * 0.005) * 2;
        continue;
      }

      const target = ch.config.path[ch.targetIndex];
      const dx = target.x - ch.x;
      const dy = target.y - ch.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < 3) {
        ch.x = target.x;
        ch.y = target.y;
        ch.waitTimer = 120 + Math.random() * 60; // pause 2-3 sec at 60fps
        ch.targetIndex = (ch.targetIndex + 1) % ch.config.path.length;
      } else {
        const move = ch.config.speed * dt;
        ch.x += (dx / dist) * move;
        ch.y += (dy / dist) * move;
      }

      ch.graphic.position.set(ch.x, ch.y);
    }
  }

  destroy(): void {
    this.container.destroy({ children: true });
  }
}
```

- [ ] **Step 2: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/engine/layers/CharacterLayer.ts
git commit -m "feat(frontend): add CharacterLayer with walking engineers"
```

---

### Task 8: CityScene Orchestrator

**Files:**
- Create: `src/engine/CityScene.ts`

- [ ] **Step 1: Implement CityScene that ties layers together**

Create `src/engine/CityScene.ts`:
```typescript
import { Application } from "pixi.js";
import { BackgroundLayer } from "@/engine/layers/BackgroundLayer";
import { BuildingLayer } from "@/engine/layers/BuildingLayer";
import { ConnectionLayer } from "@/engine/layers/ConnectionLayer";
import { CharacterLayer } from "@/engine/layers/CharacterLayer";
import { CANVAS_WIDTH, CANVAS_HEIGHT } from "@/engine/config";
import type { SceneState } from "@/types/scene";

export class CityScene {
  private app: Application;
  private background: BackgroundLayer;
  private buildings: BuildingLayer;
  private connections: ConnectionLayer;
  private characters: CharacterLayer;
  private initialized = false;

  constructor() {
    this.app = new Application();
    this.background = new BackgroundLayer();
    this.buildings = new BuildingLayer();
    this.connections = new ConnectionLayer();
    this.characters = new CharacterLayer();
  }

  async init(container: HTMLElement): Promise<void> {
    await this.app.init({
      width: CANVAS_WIDTH,
      height: CANVAS_HEIGHT,
      backgroundColor: 0x0a0e1a,
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });

    container.appendChild(this.app.canvas as HTMLCanvasElement);

    this.app.stage.addChild(this.background.container);
    this.app.stage.addChild(this.buildings.container);
    this.app.stage.addChild(this.connections.container);
    this.app.stage.addChild(this.characters.container);

    this.app.ticker.add((ticker) => {
      const dt = ticker.deltaTime;
      this.buildings.update(dt);
      this.connections.update(dt);
      this.characters.update(dt);
    });

    this.fitToContainer(container);
    this.initialized = true;
  }

  private fitToContainer(container: HTMLElement): void {
    const resize = () => {
      const { clientWidth, clientHeight } = container;
      const scale = Math.min(clientWidth / CANVAS_WIDTH, clientHeight / CANVAS_HEIGHT);
      const canvas = this.app.canvas as HTMLCanvasElement;
      canvas.style.width = `${CANVAS_WIDTH * scale}px`;
      canvas.style.height = `${CANVAS_HEIGHT * scale}px`;
    };
    resize();
    window.addEventListener("resize", resize);
  }

  transitionTo(_state: SceneState): void {
    // Phase 2 will implement visual transitions per state
  }

  destroy(): void {
    if (this.initialized) {
      this.background.destroy();
      this.buildings.destroy();
      this.connections.destroy();
      this.characters.destroy();
      this.app.destroy(true);
    }
  }
}
```

- [ ] **Step 2: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/engine/CityScene.ts
git commit -m "feat(frontend): add CityScene orchestrator (layers + ticker + resize)"
```

---

### Task 9: CityCanvas React Wrapper

**Files:**
- Create: `src/components/CityCanvas.tsx`

- [ ] **Step 1: Implement CityCanvas component**

Create `src/components/CityCanvas.tsx`:
```typescript
import { useEffect, useRef } from "react";
import { CityScene } from "@/engine/CityScene";
import { useSceneStore } from "@/store/sceneStore";

export function CityCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<CityScene | null>(null);
  const sceneState = useSceneStore((s) => s.state);

  useEffect(() => {
    const scene = new CityScene();
    sceneRef.current = scene;
    scene.init(containerRef.current!);
    return () => {
      scene.destroy();
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    sceneRef.current?.transitionTo(sceneState);
  }, [sceneState]);

  return <div ref={containerRef} className="city-canvas" />;
}
```

- [ ] **Step 2: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/components/CityCanvas.tsx
git commit -m "feat(frontend): add CityCanvas React wrapper component"
```

---

### Task 10: Sidebar Shell

**Files:**
- Create: `src/components/Sidebar.tsx`

- [ ] **Step 1: Implement basic Sidebar**

Create `src/components/Sidebar.tsx`:
```typescript
import { useSceneStore } from "@/store/sceneStore";
import { BUILDINGS } from "@/engine/config";

export function Sidebar() {
  const state = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);

  return (
    <div className="sidebar">
      <h1 className="sidebar-title">AI OPERATIONS CENTER</h1>

      <section className="sidebar-section">
        <h2>SYSTEMS OVERVIEW</h2>
        <ul className="system-list">
          {BUILDINGS.map((b) => (
            <li key={b.id} className="system-item">
              <span
                className="status-dot"
                style={{
                  backgroundColor:
                    affectedService === b.id ? "#ef5350" : "#4caf50",
                }}
              />
              <span className="system-label">{b.label}</span>
              <span className="system-status">
                {affectedService === b.id ? "ALERT" : "HEALTHY"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="sidebar-section">
        <h2>AI AGENT STATUS</h2>
        <div className="agent-status">
          <span className="agent-indicator" />
          <span>{state === "HEALTHY" ? "Idle" : state}</span>
        </div>
        <p className="agent-message">
          {state === "HEALTHY"
            ? "Monitoring system activity. No issues detected."
            : `Active — Processing ${state.toLowerCase().replace("_", " ")}...`}
        </p>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add src/components/Sidebar.tsx
git commit -m "feat(frontend): add Sidebar shell with systems overview"
```

---

### Task 11: Theme CSS & App Layout

**Files:**
- Create: `src/styles/theme.css`
- Modify: `src/app/App.tsx`

- [ ] **Step 1: Create theme.css**

Create `src/styles/theme.css`:
```css
:root {
  --bg-primary: #0a0e1a;
  --bg-secondary: #0d1225;
  --bg-sidebar: #0f1429;
  --text-primary: #e0e0e0;
  --text-secondary: #9e9e9e;
  --accent-green: #4caf50;
  --accent-cyan: #26c6da;
  --accent-red: #ef5350;
  --font-mono: "JetBrains Mono", "IBM Plex Mono", "Fira Code", monospace;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #root {
  height: 100%;
  overflow: hidden;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.app-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
}

.city-canvas {
  flex: 7;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--bg-primary);
}

.sidebar {
  flex: 3;
  background: var(--bg-sidebar);
  border-left: 1px solid #1a2744;
  padding: 24px 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.sidebar-title {
  font-size: 14px;
  letter-spacing: 2px;
  color: var(--accent-cyan);
  text-transform: uppercase;
}

.sidebar-section h2 {
  font-size: 11px;
  letter-spacing: 1.5px;
  color: var(--text-secondary);
  margin-bottom: 12px;
  text-transform: uppercase;
}

.system-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.system-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.system-label {
  flex: 1;
}

.system-status {
  font-size: 11px;
  color: var(--text-secondary);
}

.agent-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 8px;
}

.agent-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent-green);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.agent-message {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
```

- [ ] **Step 2: Update App.tsx with layout**

Replace `src/app/App.tsx` with:
```typescript
import { CityCanvas } from "@/components/CityCanvas";
import { Sidebar } from "@/components/Sidebar";
import "@/styles/theme.css";

export function App() {
  return (
    <div className="app-layout">
      <CityCanvas />
      <Sidebar />
    </div>
  );
}
```

- [ ] **Step 3: Verify compiles**

Run: `cd src_frontend/app && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/styles/theme.css src/app/App.tsx
git commit -m "feat(frontend): add dark theme CSS and app layout (70/30 split)"
```

---

### Task 12: Verify Dev Server

- [ ] **Step 1: Start dev server and verify rendering**

Run: `cd src_frontend/app && npm run dev`

Open http://localhost:3000 in browser. Verify:
- Dark background with stars
- 7 colored building rectangles with labels
- Green lines with flowing particles between buildings
- 3 colored character shapes walking between waypoints
- Right sidebar with system overview and agent status

- [ ] **Step 2: Verify 60fps**

Open DevTools → Performance tab. Record 3 seconds of animation. Confirm frame rate is consistently 55-60fps.

- [ ] **Step 3: Final commit (if any cleanup needed)**

```bash
git add -A
git commit -m "feat(frontend): Phase 1 complete — animated city with buildings, connections, characters"
```

---

## Self-Review Checklist

- [x] All spec Phase 1 requirements covered: buildings, connections, characters, PixiJS canvas, Zustand store, sidebar shell
- [x] No placeholders — all code is complete and implementable
- [x] Type consistency: `SceneState`, `BuildingConfig`, `ConnectionConfig`, `CharacterConfig` used consistently
- [x] Method names consistent: `update(dt)`, `destroy()`, `transitionTo(state)` across all layers
- [x] File paths match spec's proposed structure (with minor simplification: no effects layer in Phase 1 since spec says "Ambient twinkle" which is covered by background stars + building glow)
