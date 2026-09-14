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
/** Where the "G" key auto-walks the player: in front of the bridge, facing −z. */
export const LINK_STAND_POINT = { position: [0, 1.7, 7.0] as Vec3, yaw: 0 };

export const NOC_WALL = { position: [0, 2.2, -19.7] as Vec3, width: 10, height: 3, htmlScale: 0.01 };
