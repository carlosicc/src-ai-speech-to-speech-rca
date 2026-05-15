import type { BuildingConfig, ConnectionConfig, CharacterConfig } from "@/types/scene";

// Room layout: cross-section building, 3 floors x variable rooms
// Each room = an AWS service
export interface RoomConfig {
  id: string;
  label: string;
  floor: number;
  x: number;
  width: number;
  color: string;
  furniture: FurnitureItem[];
}

export interface FurnitureItem {
  sprite: string;
  xOffset: number;
  yOffset: number;
}

// Layout constants (in pixel units, will be scaled)
export const ROOM_HEIGHT = 72;
export const FLOOR_GAP = 5;
export const BUILDING_X = 20;
export const BUILDING_WIDTH = 440;
export const SCALE = 3;

export const ROOMS: RoomConfig[] = [
  // Floor 2 (top) — Control & Monitoring
  {
    id: "monitoring",
    label: "NOC / Monitoring",
    floor: 2,
    x: 0,
    width: 220,
    color: "#1a2744",
    furniture: [
      { sprite: "table-long.png", xOffset: 40, yOffset: 62 },
      { sprite: "laptop.png", xOffset: 45, yOffset: 55 },
      { sprite: "laptop.png", xOffset: 60, yOffset: 55 },
      { sprite: "shelf-large.png", xOffset: 30, yOffset: 18 },
      { sprite: "light-3.png", xOffset: 100, yOffset: 2 },
      { sprite: "window-square.png", xOffset: 130, yOffset: 20 },
      { sprite: "bookshelf.png", xOffset: 180, yOffset: 49 },
    ],
  },
  {
    id: "network",
    label: "Network / Gateway",
    floor: 2,
    x: 220,
    width: 220,
    color: "#1a3a3a",
    furniture: [
      { sprite: "cabinet.png", xOffset: 25, yOffset: 49 },
      { sprite: "cabinet.png", xOffset: 45, yOffset: 49 },
      { sprite: "light-2.png", xOffset: 100, yOffset: 2 },
      { sprite: "table-medium.png", xOffset: 110, yOffset: 62 },
      { sprite: "laptop.png", xOffset: 113, yOffset: 55 },
      { sprite: "window-circle.png", xOffset: 155, yOffset: 20 },
    ],
  },
  // Floor 1 (middle) — Core Services
  {
    id: "aurora-db",
    label: "Aurora DB (Server Room)",
    floor: 1,
    x: 0,
    width: 155,
    color: "#1a1a3a",
    furniture: [
      { sprite: "cabinet.png", xOffset: 15, yOffset: 49 },
      { sprite: "cabinet.png", xOffset: 35, yOffset: 49 },
      { sprite: "cabinet.png", xOffset: 55, yOffset: 49 },
      { sprite: "cabinet.png", xOffset: 75, yOffset: 49 },
      { sprite: "cabinet.png", xOffset: 110, yOffset: 49 },
      { sprite: "light-1.png", xOffset: 40, yOffset: 2 },
      { sprite: "light-1.png", xOffset: 90, yOffset: 2 },
    ],
  },
  {
    id: "ecs-cluster",
    label: "ECS Cluster",
    floor: 1,
    x: 155,
    width: 155,
    color: "#2a1a3a",
    furniture: [
      { sprite: "table-long.png", xOffset: 25, yOffset: 62 },
      { sprite: "laptop.png", xOffset: 30, yOffset: 55 },
      { sprite: "laptop.png", xOffset: 48, yOffset: 55 },
      { sprite: "bookshelf.png", xOffset: 100, yOffset: 49 },
      { sprite: "light-2.png", xOffset: 65, yOffset: 2 },
      { sprite: "window-square.png", xOffset: 90, yOffset: 20 },
    ],
  },
  {
    id: "lambda",
    label: "Lambda / Functions",
    floor: 1,
    x: 310,
    width: 130,
    color: "#1a3a2a",
    furniture: [
      { sprite: "shelf-large.png", xOffset: 15, yOffset: 18 },
      { sprite: "table-medium.png", xOffset: 40, yOffset: 62 },
      { sprite: "laptop.png", xOffset: 43, yOffset: 55 },
      { sprite: "light-1.png", xOffset: 60, yOffset: 2 },
      { sprite: "drawer.png", xOffset: 90, yOffset: 59 },
    ],
  },
  // Floor 0 (ground) — Support
  {
    id: "api-gateway",
    label: "API Gateway (Lobby)",
    floor: 0,
    x: 0,
    width: 230,
    color: "#2a2a1a",
    furniture: [
      { sprite: "couch-blue.png", xOffset: 30, yOffset: 59 },
      { sprite: "coffee-table.png", xOffset: 70, yOffset: 62 },
      { sprite: "lamp-stand.png", xOffset: 100, yOffset: 50 },
      { sprite: "bookshelf.png", xOffset: 150, yOffset: 49 },
      { sprite: "window-square.png", xOffset: 175, yOffset: 20 },
      { sprite: "light-3.png", xOffset: 80, yOffset: 2 },
    ],
  },
  {
    id: "s3-storage",
    label: "S3 Storage",
    floor: 0,
    x: 230,
    width: 210,
    color: "#3a2a1a",
    furniture: [
      { sprite: "cabinet.png", xOffset: 20, yOffset: 49 },
      { sprite: "cabinet.png", xOffset: 40, yOffset: 49 },
      { sprite: "cabinet.png", xOffset: 60, yOffset: 49 },
      { sprite: "fridge.png", xOffset: 110, yOffset: 49 },
      { sprite: "shelf-large.png", xOffset: 130, yOffset: 18 },
      { sprite: "light-2.png", xOffset: 90, yOffset: 2 },
    ],
  },
];

// NPC sprite layout: 64x48, 16x16 frames
// Row 0: front walk (4 frames)
// Row 1: side walk (3 frames + 1 empty)
// Row 2: back walk (2 frames + 2 empty)
export const NPC_FRAME_SIZE = 16;
export const NPC_SHEETS = [
  "/sprites/characters/npc-male.png",
  "/sprites/characters/npc-female.png",
  "/sprites/characters/artun.png",
  "/sprites/characters/hana.png",
  "/sprites/characters/grym.png",
  "/sprites/characters/julz.png",
  "/sprites/characters/nyro.png",
  "/sprites/characters/khali.png",
  "/sprites/characters/serek.png",
];

// Which sheets use the PixelSpaces layout (16x16, 4c x 3r) vs OldTown layout (16x16, 4c x 31r)
export const PIXELSPACES_NPC_COUNT = 2;

export const CHARACTERS: CharacterConfig[] = [
  { id: "citizen-1", color: "#4ecdc4", speed: 0.4 },
  { id: "citizen-2", color: "#f7dc6f", speed: 0.3 },
  { id: "citizen-3", color: "#af7ac5", speed: 0.35 },
  { id: "citizen-4", color: "#f1948a", speed: 0.45 },
  { id: "citizen-5", color: "#76d7c4", speed: 0.3 },
  { id: "citizen-6", color: "#7fb3d3", speed: 0.4 },
  { id: "citizen-7", color: "#e59866", speed: 0.35 },
];

// Legacy exports for type compat
export const BUILDINGS: BuildingConfig[] = ROOMS.map((r) => ({
  id: r.id,
  label: r.label,
  xPct: 0,
  yPct: 0,
  width: r.width,
  height: ROOM_HEIGHT,
  color: r.color,
}));

export const CONNECTIONS: ConnectionConfig[] = [];
