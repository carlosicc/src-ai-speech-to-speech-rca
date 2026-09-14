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
