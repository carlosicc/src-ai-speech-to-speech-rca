import type { SceneState } from "@/types/scene";

export interface RoomOverlay {
  color: string;
  alpha: number;
}

export function getRoomOverlay(
  roomId: string,
  affectedRoom: string | null,
  state: SceneState,
  time: number
): RoomOverlay | null {
  const isAffected = roomId === affectedRoom;

  switch (state) {
    case "HEALTHY":
    case "RESOLVED":
      return null;

    case "INCIDENT_DETECTED":
      if (isAffected) {
        const flash = 0.25 + Math.sin(time * 0.15) * 0.1;
        return { color: "#ff0000", alpha: flash };
      }
      return { color: "#000000", alpha: 0.15 };

    case "DIAGNOSING":
      if (isAffected) {
        const pulse = 0.2 + Math.sin(time * 0.1) * 0.08;
        return { color: "#ff6600", alpha: pulse };
      }
      return null;

    case "CALLING":
      if (isAffected) {
        return { color: "#ff0000", alpha: 0.2 };
      }
      return null;

    case "RECOVERING":
      if (isAffected) {
        const flicker = Math.random() > 0.7 ? 0.12 : 0;
        return { color: "#ff0000", alpha: flicker };
      }
      return null;
  }
}

export type CharBehavior = "walk" | "idle" | "panic";

export function getCharacterBehavior(
  charRoom: string,
  affectedRoom: string | null,
  state: SceneState
): CharBehavior {
  const isInAffected = charRoom === affectedRoom;

  switch (state) {
    case "HEALTHY":
    case "RESOLVED":
      return "walk";
    case "INCIDENT_DETECTED":
      return isInAffected ? "panic" : "idle";
    case "DIAGNOSING":
      return isInAffected ? "panic" : "idle";
    case "CALLING":
    case "RECOVERING":
      return "idle";
  }
}
