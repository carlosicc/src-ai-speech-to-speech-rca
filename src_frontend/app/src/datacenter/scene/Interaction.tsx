import { useEffect } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { Raycaster, Vector2 } from "three";
import { isTypingInField } from "@/datacenter/lib/useKeyboard";
import { LINK_TARGET_NAME } from "@/datacenter/scene/ServiceLink";
import { useDataCenterUiStore } from "@/datacenter/store/dataCenterUiStore";
import { canDisconnect, useInfrastructureStore } from "@/store/infrastructureStore";
import { useSceneStore } from "@/store/sceneStore";

const INTERACT_DISTANCE = 2.6;
const raycaster = new Raycaster();
const screenCenter = new Vector2(0, 0);

export function Interaction() {
  const camera = useThree((s) => s.camera);
  const scene = useThree((s) => s.scene);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.repeat || isTypingInField() || e.key.toLowerCase() !== "e") return;
      const ui = useDataCenterUiStore.getState();
      const infra = useInfrastructureStore.getState();
      const allowed = canDisconnect(useSceneStore.getState().state, infra.link, infra.pendingRequestId);
      if (ui.mode === "walk" && ui.lookingAtLink && allowed) ui.holdDispatch({ type: "press" });
    };
    const up = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "e") useDataCenterUiStore.getState().holdDispatch({ type: "release" });
    };
    const blur = () => useDataCenterUiStore.getState().holdDispatch({ type: "cancel" });
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  }, []);

  useFrame((_, dt) => {
    const ui = useDataCenterUiStore.getState();

    if (ui.mode === "walk") {
      raycaster.setFromCamera(screenCenter, camera);
      raycaster.far = INTERACT_DISTANCE;
      const target = scene.getObjectByName(LINK_TARGET_NAME);
      const looking = target ? raycaster.intersectObject(target, false).length > 0 : false;
      if (looking !== ui.lookingAtLink) ui.setLookingAtLink(looking);
      if (!looking && ui.hold.holding) ui.holdDispatch({ type: "cancel" });
    } else if (ui.lookingAtLink) {
      ui.setLookingAtLink(false);
    }

    if (ui.hold.holding) ui.holdDispatch({ type: "tick", dt: Math.min(dt, 0.05) });
  });

  return null;
}
