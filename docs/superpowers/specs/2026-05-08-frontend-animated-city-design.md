# Frontend — Animated City Dashboard Design

**Date**: 2026-05-08  
**Status**: Draft  
**Author**: Carlos / Claude

---

## Context

This is the frontend for the "Alert to Action" RCA Agent Demo at AWS Summit Milan 2026. The UI needs to be visually striking for booth traffic — an animated pixel-art city that shows infrastructure health at a glance, then dramatically reacts when an incident occurs.

The frontend is a display-first UI (not heavily interactive). Booth visitors watch the demo loop; the only interaction is optionally triggering an incident or volunteering a phone number.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  React App (Vite + TypeScript)                                       │
│                                                                       │
│  ┌─────────────────────────────────┐  ┌──────────────────────────┐  │
│  │  CityCanvas (PixiJS)            │  │  Sidebar (Cloudscape)    │  │
│  │  ~70% width                     │  │  ~30% width              │  │
│  │                                 │  │                          │  │
│  │  Layers:                        │  │  - Systems Overview      │  │
│  │  1. Background (static)         │  │  - Live Metrics          │  │
│  │  2. Buildings (sprites)         │  │  - AI Agent Status       │  │
│  │  3. Connections (animated)      │  │  - Call Transcript       │  │
│  │  4. Characters (animated)       │  │  - Demo Controls         │  │
│  │  5. Effects (particles)         │  │                          │  │
│  └─────────────────────────────────┘  └──────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  State Manager (Zustand)                                         │ │
│  │  sceneState: HEALTHY | INCIDENT | DIAGNOSING | CALLING | RESOLVED│ │
│  │  Drives both PixiJS scene + Sidebar reactively                   │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  WebSocket Client (future)                                       │ │
│  │  Receives state changes from backend → updates Zustand store     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Animated City (Steady State)

**Goal**: A PixiJS canvas showing a pixel-art city with buildings, animated connection lines, and walking characters. Everything looks healthy and alive.

### Scene Composition

| Layer | Z-Index | Content | Animation |
|-------|---------|---------|-----------|
| Background | 0 | Dark city ground/sky (single AI-generated PNG) | None (static) |
| Buildings | 1 | 6-8 labeled building sprites placed on grid | Subtle glow pulse (CSS filter or PixiJS filter) |
| Connections | 2 | Glowing lines between buildings | Particles flowing along paths (data flow effect) |
| Characters | 3 | 3-4 pixel engineer sprites | Walk along predefined paths, idle animations |
| UI Overlays | 4 | Building labels, status indicators | Fade in/out |

### Buildings (Services)

| Building | Label | Position (approx) |
|----------|-------|--------------------|
| Data Center | "Aurora DB" | Center-left |
| API Gateway | "API Gateway" | Center |
| Network Tower | "Network" | Center-right |
| Server Rack | "ECS Cluster" | Bottom-left |
| Lambda | "Lambda Functions" | Bottom-center |
| Storage | "S3 Storage" | Bottom-center-right |
| Monitor | "Monitoring" | Bottom-right |

### Character Animations

Each character has a sprite sheet with frames for:
- **Walk right** (4 frames)
- **Walk left** (4 frames, or mirror)
- **Idle** (2 frames, subtle bounce)

Characters follow predefined bezier paths between buildings, pausing at each for 2-3 seconds (idle animation) before walking to the next.

### Connection Lines

Animated "data flow" lines between connected buildings:
- Rendered as dashed lines with particles moving along them
- Green/cyan color in healthy state
- Subtle glow effect (PixiJS blur filter on a line graphic)

### Art Assets Required

All generated as pixel-art PNGs (transparent background, consistent palette):

```
public/sprites/
├── background.png          (1920x1080, dark city ground + sky)
├── buildings/
│   ├── data-center.png     (~128x128)
│   ├── api-gateway.png     (~128x128)
│   ├── network-tower.png   (~128x96)
│   ├── server-rack.png     (~128x128)
│   ├── lambda.png          (~96x96)
│   ├── s3-storage.png      (~96x96)
│   └── monitoring.png      (~96x96)
├── characters/
│   ├── engineer-1.png      (sprite sheet: 4 cols x 3 rows = walk-right, walk-left, idle)
│   ├── engineer-2.png      (same format, different character)
│   └── engineer-3.png      (same format, different character)
└── effects/
    ├── particle-green.png  (8x8 glow dot)
    ├── particle-red.png    (8x8 glow dot)
    └── spark.png           (16x16 spark sprite)
```

### PixiJS Integration with React

```typescript
// CityCanvas.tsx — thin React wrapper
export function CityCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<CityScene | null>(null);
  const sceneState = useSceneStore((s) => s.state);

  useEffect(() => {
    // Initialize PixiJS Application once
    const scene = new CityScene(containerRef.current!);
    sceneRef.current = scene;
    return () => scene.destroy();
  }, []);

  useEffect(() => {
    // React to state changes
    sceneRef.current?.transitionTo(sceneState);
  }, [sceneState]);

  return <div ref={containerRef} className="city-canvas" />;
}
```

The `CityScene` class manages all PixiJS logic (sprite loading, animation loops, state transitions) — completely decoupled from React rendering.

---

## Phase 2: Incident Mode

**Goal**: When state changes to `INCIDENT`, the city reacts dramatically. Characters panic, buildings go dark, connections flash red. Initially triggered by a mock button; later by WebSocket.

### State Machine

```
HEALTHY → INCIDENT_DETECTED → DIAGNOSING → CALLING → RECOVERING → RESOLVED → HEALTHY
   ↑                                                                              │
   └──────────────────────────────────────────────────────────────────────────────┘
                                    (auto-reset after 10s)
```

### Visual Transitions

| State | Buildings | Connections | Characters | Effects |
|-------|-----------|-------------|------------|---------|
| HEALTHY | All glowing green | Green particles flowing | Walking calmly | Ambient twinkle |
| INCIDENT_DETECTED | Target goes dark/red | Target connections flash red | Nearby chars → panic anim | Screen flash, sparks on building |
| DIAGNOSING | Target pulses orange | Scan effect on connections | One char runs to building | Magnifying glass icon appears |
| CALLING | Target still red | Phone icon pulses | Chars look at phone | Ring animation |
| RECOVERING | Target flickers green | Connections restore one-by-one | Chars watch hopefully | Loading spinner |
| RESOLVED | All green restored | All flowing green | Chars celebrate (jump) | Confetti particles |

### Character Panic Animation

Additional sprite sheet frames needed:
- **Panic** (4 frames: arms up, running in small circle)
- **Celebrate** (4 frames: jumping with arms raised)

### Triggering Mechanism

```typescript
// State store (Zustand)
interface SceneStore {
  state: SceneState;
  affectedService: string | null;
  triggerIncident: (service: string) => void;
  advancePhase: () => void;
  reset: () => void;
}
```

Phase 2 includes a hidden dev panel (keyboard shortcut `Ctrl+D`) with buttons to:
- Trigger incident on a specific service
- Advance to next phase manually
- Reset to healthy

Later, `triggerIncident` is called from the WebSocket message handler — zero code change needed in the scene.

---

## Phase 3: Right Sidebar

**Goal**: A dark-themed dashboard panel showing system metrics, AI agent status, and eventually the live call transcript.

### Layout

```
┌──────────────────────────────┐
│  AI OPERATIONS CENTER (logo) │
├──────────────────────────────┤
│  SYSTEMS OVERVIEW            │
│  ● Aurora DB      HEALTHY    │
│  ● API Gateway    HEALTHY    │
│  ● ECS Payments   HEALTHY    │
│  ● Lambda Auth    HEALTHY    │
│  ● S3 Storage     HEALTHY    │
├──────────────────────────────┤
│  LIVE METRICS                │
│  CPU ████░░░░ 23%     99.99% │
│  MEM ██████░░ 41%     uptime │
│  RPS ─────── 1.2k           │
│  Conn ────── 842            │
├──────────────────────────────┤
│  AI AGENT STATUS             │
│  ◉ Idle                      │
│  Monitoring system activity. │
│  No issues detected.         │
├──────────────────────────────┤
│  CALL TRANSCRIPT (Phase 4+)  │
│  (hidden until call starts)  │
└──────────────────────────────┘
```

### Styling

- Dark background matching the city aesthetic (#0a0e1a or similar)
- Monospace/tech font (JetBrains Mono or IBM Plex Mono)
- Cyan/green accent colors matching the pixel-art palette
- Cloudscape components with custom dark theme override (CSS custom properties)
- Sparkline charts: lightweight inline SVG (no heavy charting library)

### Metrics Data

Phase 3 uses mock data generators that produce realistic-looking metrics:
- CPU/Memory: slowly fluctuating random values
- RPS: sine wave with noise
- Connections: stable with occasional small jumps

During an incident, metrics react: CPU spikes, connections drop, RPS goes to zero on the affected service.

### Integration with Scene State

The sidebar reads from the same Zustand store as the PixiJS scene:
- HEALTHY → all green dots, "Idle" agent status
- INCIDENT → affected service dot goes red, agent status changes to "ACTIVE — Detecting anomaly..."
- DIAGNOSING → agent status: "Diagnosing — Pulling logs from {service}..."
- CALLING → agent status: "Escalating — Calling on-call engineer..."
- RESOLVED → all dots back to green, agent status: "Resolved — Incident cleared"

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Animation engine | PixiJS v8 | Purpose-built for 2D sprite rendering, WebGL performance, lightweight |
| State management | Zustand | Minimal boilerplate, works outside React (PixiJS can subscribe), tiny bundle |
| Sprite art | AI-generated PNGs | Custom look, fast iteration, consistent pixel-art style |
| Sidebar components | Cloudscape (dark theme) | Matches reference repos, AWS-native look |
| Sparkline charts | Inline SVG (hand-rolled) | No library needed for simple lines, tiny footprint |
| React-PixiJS bridge | Ref-based (no @pixi/react) | Cleaner separation, avoids reconciler overhead for 60fps animation |

---

## File Structure

```
src_frontend/app/src/
├── app/
│   ├── main.tsx
│   └── App.tsx
├── components/
│   ├── CityCanvas.tsx          ← React wrapper for PixiJS
│   ├── Sidebar.tsx             ← Right panel container
│   ├── SystemsOverview.tsx     ← Status dots
│   ├── LiveMetrics.tsx         ← Sparklines + numbers
│   ├── AgentStatus.tsx         ← AI agent state display
│   └── DevPanel.tsx            ← Hidden debug controls
├── engine/
│   ├── CityScene.ts            ← Main PixiJS scene orchestrator
│   ├── layers/
│   │   ├── BackgroundLayer.ts  ← Static background
│   │   ├── BuildingLayer.ts    ← Building sprites + labels
│   │   ├── ConnectionLayer.ts  ← Animated data flow lines
│   │   ├── CharacterLayer.ts   ← Walking/idle characters
│   │   └── EffectsLayer.ts     ← Particles, sparks, confetti
│   ├── sprites/
│   │   ├── Building.ts         ← Building sprite class
│   │   ├── Character.ts        ← Character with state machine
│   │   └── Particle.ts         ← Reusable particle
│   └── config.ts               ← Positions, paths, timing constants
├── store/
│   └── sceneStore.ts           ← Zustand store (state machine)
├── lib/
│   ├── websocket.ts            ← WebSocket client (future)
│   └── mockMetrics.ts          ← Fake metric generators
├── types/
│   └── scene.ts                ← SceneState, Building, Character types
└── styles/
    └── theme.css               ← Dark theme overrides
```

---

## Success Criteria

| Phase | Done When |
|-------|-----------|
| Phase 1 | City renders in browser with buildings, flowing connections, and walking characters. Runs at 60fps. |
| Phase 2 | Pressing a button triggers incident → buildings go red, characters panic, then auto-resolves. State machine drives all transitions. |
| Phase 3 | Right sidebar shows system status, metrics (animated sparklines), and AI agent status. All react to state changes in sync with the city. |

---

## Out of Scope (Future Phases)

- Real WebSocket connection to backend (Phase 4)
- Live call transcript display (Phase 4)
- Volunteer phone number input (Phase 4)
- Audio/sound effects (nice-to-have)
- Mobile responsiveness (booth display is fixed resolution)
