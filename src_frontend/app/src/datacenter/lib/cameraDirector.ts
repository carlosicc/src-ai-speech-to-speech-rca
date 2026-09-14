import type { Vec3 } from "@/datacenter/config/layout";
import type { SceneState } from "@/types/scene";

export interface Shot {
  position: Vec3;
  target: Vec3;
}

const AURORA_RACK: Vec3 = [3.5, 1.2, 3];
const LINK_BRIDGE: Vec3 = [0, 0.4, 4.6];
const NOC_SCREEN: Vec3 = [0, 2.2, -19.7];
const ORBIT_RADIUS = 13;
const ORBIT_SPEED = 0.08;

/** Phase-driven cinematic camera. `t` is elapsed seconds. */
export function shotForPhase(phase: SceneState, t: number): Shot {
  switch (phase) {
    case "HEALTHY": {
      const a = t * ORBIT_SPEED;
      return { position: [Math.sin(a) * ORBIT_RADIUS, 3.8, Math.cos(a) * ORBIT_RADIUS], target: [0, 1, 0] };
    }
    case "INCIDENT_DETECTED":
    case "DIAGNOSING":
      return { position: [1.5, 2.4, 8.5], target: AURORA_RACK };
    case "CALLING":
      return { position: [0, 2.6, -11], target: NOC_SCREEN };
    case "RECOVERING":
      return { position: [0.8, 1.6, 7.8], target: LINK_BRIDGE };
    case "RESOLVED":
      return { position: [0, 3.9, 16], target: [0, 1, -2] };
  }
}
