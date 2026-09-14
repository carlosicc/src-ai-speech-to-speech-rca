import { describe, expect, it } from "vitest";
import { shotForPhase } from "@/datacenter/lib/cameraDirector";
import type { SceneState } from "@/types/scene";

const PHASES: SceneState[] = ["HEALTHY", "INCIDENT_DETECTED", "DIAGNOSING", "CALLING", "RECOVERING", "RESOLVED"];

describe("shotForPhase", () => {
  it("orbits slowly while HEALTHY", () => {
    const a = shotForPhase("HEALTHY", 0);
    const b = shotForPhase("HEALTHY", 10);
    expect(a.position).not.toEqual(b.position);
    const r = Math.hypot(a.position[0], a.position[2]);
    expect(r).toBeCloseTo(13, 5);
  });

  it("holds a fixed shot in every incident phase", () => {
    for (const p of PHASES.filter((p) => p !== "HEALTHY")) {
      expect(shotForPhase(p, 0)).toEqual(shotForPhase(p, 42));
    }
  });

  it("keeps the camera inside the room", () => {
    for (const p of PHASES) {
      const { position } = shotForPhase(p, 7);
      expect(Math.abs(position[0])).toBeLessThan(15);
      expect(Math.abs(position[2])).toBeLessThan(20);
      expect(position[1]).toBeGreaterThan(0.5);
      expect(position[1]).toBeLessThan(4.2);
    }
  });
});
