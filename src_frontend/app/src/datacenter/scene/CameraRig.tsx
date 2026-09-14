import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { MathUtils, Vector3 } from "three";
import { LINK_STAND_POINT, PLAYER, RACK_BOXES, WALK_BOUNDS } from "@/datacenter/config/layout";
import { shotForPhase } from "@/datacenter/lib/cameraDirector";
import { resolveMove } from "@/datacenter/lib/collision";
import { isTypingInField, useKeyboard } from "@/datacenter/lib/useKeyboard";
import { useDataCenterUiStore } from "@/datacenter/store/dataCenterUiStore";
import { useSceneStore } from "@/store/sceneStore";

const WALK_SPEED = 2.2; // m/s
const SPRINT_MULT = 1.8;
const TURN_SPEED = 1.6; // rad/s
const DIRECTOR_DAMP = 2.5;
const AUTOWALK_DAMP = 3;
const MAX_STEP = 0.05;

const shotPos = new Vector3();
const shotTarget = new Vector3();

export function CameraRig() {
  const camera = useThree((s) => s.camera);
  const keys = useKeyboard();
  const mode = useDataCenterUiStore((s) => s.mode);

  const yaw = useRef<number>(PLAYER.spawnYaw);
  const pos = useRef(new Vector3(...PLAYER.spawn));
  const lookAt = useRef(new Vector3(0, 1, 0));
  const autoWalkTarget = useRef<Vector3 | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTypingInField() || e.repeat) return;
      const k = e.key.toLowerCase();
      const ui = useDataCenterUiStore.getState();
      if (k === "v") ui.toggleMode();
      if (k === "g") {
        ui.setMode("walk");
        autoWalkTarget.current = new Vector3(...LINK_STAND_POINT.position);
      }
      if (k === "r") {
        pos.current.set(...PLAYER.spawn);
        yaw.current = PLAYER.spawnYaw;
        autoWalkTarget.current = null;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useFrame(({ clock }, dt) => {
    const step = Math.min(dt, MAX_STEP);

    if (mode === "director") {
      const shot = shotForPhase(useSceneStore.getState().state, clock.elapsedTime);
      shotPos.set(...shot.position);
      shotTarget.set(...shot.target);
      camera.position.x = MathUtils.damp(camera.position.x, shotPos.x, DIRECTOR_DAMP, step);
      camera.position.y = MathUtils.damp(camera.position.y, shotPos.y, DIRECTOR_DAMP, step);
      camera.position.z = MathUtils.damp(camera.position.z, shotPos.z, DIRECTOR_DAMP, step);
      lookAt.current.x = MathUtils.damp(lookAt.current.x, shotTarget.x, DIRECTOR_DAMP, step);
      lookAt.current.y = MathUtils.damp(lookAt.current.y, shotTarget.y, DIRECTOR_DAMP, step);
      lookAt.current.z = MathUtils.damp(lookAt.current.z, shotTarget.z, DIRECTOR_DAMP, step);
      camera.lookAt(lookAt.current);
      return;
    }

    const k = keys.current;
    const target = autoWalkTarget.current;
    if (target) {
      if (k.size > 0) {
        autoWalkTarget.current = null; // manual input cancels auto-walk
      } else {
        pos.current.x = MathUtils.damp(pos.current.x, target.x, AUTOWALK_DAMP, step);
        pos.current.z = MathUtils.damp(pos.current.z, target.z, AUTOWALK_DAMP, step);
        yaw.current = MathUtils.damp(yaw.current, LINK_STAND_POINT.yaw, AUTOWALK_DAMP, step);
        if (Math.hypot(pos.current.x - target.x, pos.current.z - target.z) < 0.05) autoWalkTarget.current = null;
      }
    } else {
      const turn = (k.has("arrowleft") || k.has("a") ? 1 : 0) - (k.has("arrowright") || k.has("d") ? 1 : 0);
      const fwd = (k.has("arrowup") || k.has("w") ? 1 : 0) - (k.has("arrowdown") || k.has("s") ? 1 : 0);
      yaw.current += turn * TURN_SPEED * step;
      const dist = WALK_SPEED * (k.has("shift") ? SPRINT_MULT : 1) * fwd * step;
      // yaw 0 looks toward -z
      const dx = -Math.sin(yaw.current) * dist;
      const dz = -Math.cos(yaw.current) * dist;
      const next = resolveMove(pos.current.x, pos.current.z, dx, dz, RACK_BOXES, WALK_BOUNDS);
      pos.current.x = next.x;
      pos.current.z = next.z;
    }

    camera.position.set(pos.current.x, PLAYER.eyeHeight, pos.current.z);
    camera.rotation.set(0, yaw.current, 0, "YXZ");
  });

  return null;
}
