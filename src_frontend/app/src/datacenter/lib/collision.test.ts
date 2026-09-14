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
