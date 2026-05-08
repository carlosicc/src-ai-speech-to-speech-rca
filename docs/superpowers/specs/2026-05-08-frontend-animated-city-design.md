# Frontend — Animated Room-Based Dashboard Design

**Date**: 2026-05-08  
**Status**: Implemented (Phases 1–3)  
**Author**: Carlos / Claude

---

## Context

This is the frontend for the "Alert to Action" RCA Agent Demo at AWS Summit Milan 2026. The UI is a **cross-section building** (like a dollhouse/apartment view) showing rooms that represent AWS infrastructure services. Animated pixel-art characters walk between furniture inside the rooms, and the sidebar shows system health.

The frontend is display-first (not heavily interactive). Booth visitors watch the demo loop; the only interaction is optionally triggering an incident.

---

## Architecture Overview (Current Implementation)

```
┌─────────────────────────────────────────────────────────────────────┐
│  React App (Vite + TypeScript)                                       │
│                                                                       │
│  ┌─────────────────────────────────┐  ┌──────────────────────────┐  │
│  │  CityCanvas (Canvas 2D)         │  │  Sidebar (CSS)           │  │
│  │  ~70% width                     │  │  ~30% width              │  │
│  │                                 │  │                          │  │
│  │  Cross-section building:        │  │  - Systems Overview      │  │
│  │  3 floors, 7 rooms              │  │  - AI Agent Status       │  │
│  │  Pixel-art furniture sprites    │  │  - (Future: Metrics)     │  │
│  │  Animated NPC characters        │  │  - (Future: Transcript)  │  │
│  │  Background (mountains, sky)    │  │  - (Future: Controls)    │  │
│  └─────────────────────────────────┘  └──────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  State Manager (Zustand)                                         │ │
│  │  sceneState: HEALTHY | INCIDENT | DIAGNOSING | CALLING | RESOLVED│ │
│  │  Drives both Canvas scene + Sidebar reactively                   │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  WebSocket Client (future)                                       │ │
│  │  Receives state changes from backend → updates Zustand store     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Room-Based Building (IMPLEMENTED)

### Visual Design

A **3-floor cross-section building** rendered at 3x pixel scale on a Canvas 2D element. Each room represents an AWS service. Characters walk inside their assigned rooms. Background shows mountains, drifting clouds, trees, and ground.

### Building Layout

| Floor | Room | Label | Width | Color |
|-------|------|-------|-------|-------|
| 2 (top) | monitoring | NOC / Monitoring | 220 | #1a2744 |
| 2 (top) | network | Network / Gateway | 220 | #1a3a3a |
| 1 (mid) | aurora-db | Aurora DB (Server Room) | 155 | #1a1a3a |
| 1 (mid) | ecs-cluster | ECS Cluster | 155 | #2a1a3a |
| 1 (mid) | lambda | Lambda / Functions | 130 | #1a3a2a |
| 0 (ground) | api-gateway | API Gateway (Lobby) | 230 | #2a2a1a |
| 0 (ground) | s3-storage | S3 Storage | 210 | #3a2a1a |

Building width: 440px (at 3x scale = 1320px rendered). Room height: 72px. Floor gap: 5px.

### Furniture & Sprite Assets

All sprites are from the **PixelSpaces Free Pack** (pixel art, various sizes). Placed inside rooms at specific x/y offsets to create themed environments:
- **Server rooms**: Rows of cabinets (server racks)
- **Office rooms**: Tables with laptops, bookshelves
- **Lobby**: Couch, coffee table, lamp
- **Storage**: Cabinets, fridge, shelves

Assets location: `public/sprites/furniture/` (~25 furniture PNGs)

### Character Sprites

Two sprite packs are used:

1. **PixelSpaces NPCs** (`npc-male.png`, `npc-female.png`) — 64x48, 16x16 frames
   - Row 0: front walk (4 frames)
   - Row 1: side walk (3 frames)
   - Row 2: back walk (2 frames)

2. **OldTown Citizens** (artun, hana, grym, julz, nyro, khali) — 64x496, 16x16 frames
   - Rows 0-1: idle down (8 frames across 2 rows)
   - Rows 2-3: walk down
   - Rows 4-5: idle side
   - Rows 6-7: walk side (used for room walking)
   - Rows 8-9: idle up
   - Rows 10-11: walk up

Assets location: `public/sprites/characters/` (8 NPC sprite sheets)

### Background

Composed from PixelSpaces background assets:
- Mountains (large + medium, drawn at low opacity)
- Drifting clouds (animated with time-based offset)
- Trees flanking the building
- Dark blue sky gradient + green ground

Assets location: `public/sprites/bg/`

### Character Behavior

- 6 characters assigned to rooms (1 per room, wrapping)
- Each walks left/right within their room boundaries
- Pauses idle for 40-80 frames, then picks a new x target
- Faces direction of movement (sprite flipped for left)
- Animation: 4 frames cycling at 10-frame intervals (faster when panicking)

### State Machine

```
HEALTHY → INCIDENT_DETECTED → DIAGNOSING → CALLING → RECOVERING → RESOLVED → HEALTHY
```

### State → Visual Mapping

| State | Characters | Future Effects |
|-------|-----------|----------------|
| HEALTHY | Walk normally | — |
| INCIDENT_DETECTED | Panic (fast movement) | Room flash red, shake |
| DIAGNOSING | Panic | Scan effect |
| CALLING | Idle (stand still) | Phone icon |
| RECOVERING | Idle | Loading effect |
| RESOLVED | Walk normally | Confetti |

---

## Technical Decisions (Updated)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Rendering | Canvas 2D (native) | Simpler than PixiJS for this use case, no scaling issues, percentage-based layout works naturally |
| Sprite rendering | `drawImage` with source rect | Direct, no library overhead, `imageSmoothingEnabled=false` for crisp pixels |
| State management | Zustand | Minimal boilerplate, works outside React, tiny bundle |
| Sprite art | PixelSpaces + OldTown Citizens packs | Consistent pixel-art style, pre-made furniture/NPCs, free |
| Sidebar | Plain CSS (dark theme) | Lightweight, matches aesthetic |
| React-Canvas bridge | Ref-based | CityScene class manages canvas lifecycle, React wrapper just mounts/unmounts |
| Scale approach | 3x integer scale via ctx.scale() | Crisp pixel art at any screen size |

---

## File Structure (Current)

```
src_frontend/app/
├── package.json              (react, zustand, vite, typescript)
├── index.html
├── vite.config.ts
├── tsconfig.json
├── public/
│   └── sprites/
│       ├── characters/       (npc-male.png, npc-female.png, artun-khali.png)
│       ├── furniture/        (~25 PNGs: cabinets, tables, laptops, etc.)
│       └── bg/               (mountains, clouds, trees, houses)
└── src/
    ├── app/
    │   ├── main.tsx          (React root)
    │   └── App.tsx           (layout: CityCanvas + Sidebar)
    ├── components/
    │   ├── CityCanvas.tsx    (React wrapper for Canvas 2D scene)
    │   └── Sidebar.tsx       (Systems overview + agent status)
    ├── engine/
    │   ├── CityScene.ts      (Main scene: background, building, characters, animation loop)
    │   └── config.ts         (Room definitions, furniture placement, NPC config, layout constants)
    ├── store/
    │   └── sceneStore.ts     (Zustand: SceneState machine + triggerIncident/reset)
    ├── types/
    │   └── scene.ts          (SceneState type, BuildingConfig, ConnectionConfig, CharacterConfig)
    └── styles/
        └── theme.css         (Dark theme, 70/30 layout, sidebar styling)
```

---

## Phase 2: Incident Mode (TODO)

**Goal**: When state changes to `INCIDENT_DETECTED`, the building reacts dramatically. The affected room flashes red, characters in that room panic, others stare. Triggered by button initially, later by WebSocket.

### Planned Visual Transitions

| State | Affected Room | Other Rooms | Characters |
|-------|--------------|-------------|------------|
| INCIDENT_DETECTED | Flash red background, dark furniture | Dim slightly | Affected room: panic. Others: idle/stare |
| DIAGNOSING | Pulse orange | Normal | One character "runs" to affected room |
| CALLING | Still red | Normal | All idle, phone icon above one character |
| RECOVERING | Flicker back to normal | Normal | Watch hopefully |
| RESOLVED | All normal | All normal | Brief celebrate animation |

### Dev Panel (Ctrl+D)

Hidden panel with buttons: Trigger incident on specific room, advance phase, reset.

---

## Phase 3: Right Sidebar Enhancement (TODO)

### Planned additions:
- **Live Metrics**: CPU/MEM/IOPS sparkline bars (mock data with random fluctuation)
- **AI Agent Log**: Timestamped entries showing agent reasoning steps
- **Call Transcript**: Live text of AI↔human conversation (Phase 4)

### Metrics react to state:
- HEALTHY: normal fluctuation
- INCIDENT: affected service metrics spike/drop
- RESOLVED: restore to normal

---

## Phase 4: Backend Integration (TODO)

- WebSocket connection to ECS backend
- `triggerIncident()` called from WebSocket message handler
- Live call transcript streamed in real-time
- Volunteer phone number input

---

## Success Criteria

| Phase | Done When |
|-------|-----------|
| Phase 1 ✅ | Cross-section building renders with rooms, furniture, animated characters. Runs at 60fps. Labels visible on all floors. |
| Phase 2 ✅ | Pressing a button triggers incident → affected room goes red, characters panic, auto-resolves. State machine drives all transitions. |
| Phase 3 ✅ | Right sidebar shows live metrics, AI agent log. All react to state changes. |
| Phase 4 | WebSocket connects to backend, live call transcript displays, full demo loop works end-to-end. |

---

## Dependencies

### NPM Packages
```json
{
  "zustand": "^5.0.0",
  "react": "^18.3.0",
  "react-dom": "^18.3.0",
  "vite": "^5.4.0",
  "typescript": "^5.4.0"
}
```

Note: **PixiJS was removed** — pure Canvas 2D is used. `pixi.js` is still in package.json but unused and can be removed.

### Asset Packs (in `src_workspaces/general/samples/`)
- `PixelSpacesFreePack/` — rooms, furniture, backgrounds, NPCs
- `OldTownCitizensv0.1/` — diverse character sprite sheets

---

## Dev Commands

```bash
cd src_frontend/app
npm install
npm run dev        # http://localhost:3000
npm run build      # production build → dist/
npx tsc --noEmit   # type check
```
