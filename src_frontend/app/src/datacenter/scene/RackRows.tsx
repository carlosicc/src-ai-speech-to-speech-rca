import { useLayoutEffect, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Color, InstancedMesh, Object3D } from "three";
import { FILLER_RACKS, RACK } from "@/datacenter/config/layout";

const LEDS_PER_RACK = 8;
const LED_GREEN = new Color("#22c55e");
const LED_CYAN = new Color("#22d3ee");
const LED_OFF = new Color("#0a3d1a");
const BLINK_INTERVAL_S = 0.12;
const BLINKS_PER_INTERVAL = 40;
const dummy = new Object3D();

function baseColor(k: number): Color {
  return k % 2 === 0 ? LED_GREEN : LED_CYAN;
}

export function RackRows() {
  const rackRef = useRef<InstancedMesh>(null);
  const ledRef = useRef<InstancedMesh>(null);
  const nextBlink = useRef(0);
  const ledCount = FILLER_RACKS.length * LEDS_PER_RACK;

  useLayoutEffect(() => {
    const racks = rackRef.current;
    const leds = ledRef.current;
    if (!racks || !leds) return;
    FILLER_RACKS.forEach((r, i) => {
      dummy.position.set(r.x, RACK.height / 2, r.z);
      dummy.updateMatrix();
      racks.setMatrixAt(i, dummy.matrix);
      for (let j = 0; j < LEDS_PER_RACK; j++) {
        const k = i * LEDS_PER_RACK + j;
        dummy.position.set(
          r.x - 0.28 + (j % 2) * 0.56,
          0.4 + Math.floor(j / 2) * 0.45,
          r.z + RACK.depth / 2 + 0.006,
        );
        dummy.updateMatrix();
        leds.setMatrixAt(k, dummy.matrix);
        leds.setColorAt(k, baseColor(k));
      }
    });
    racks.instanceMatrix.needsUpdate = true;
    leds.instanceMatrix.needsUpdate = true;
    if (leds.instanceColor) leds.instanceColor.needsUpdate = true;
  }, []);

  useFrame(({ clock }) => {
    const leds = ledRef.current;
    if (!leds || clock.elapsedTime < nextBlink.current) return;
    nextBlink.current = clock.elapsedTime + BLINK_INTERVAL_S;
    for (let n = 0; n < BLINKS_PER_INTERVAL; n++) {
      const k = Math.floor(Math.random() * ledCount);
      leds.setColorAt(k, Math.random() < 0.15 ? LED_OFF : baseColor(k));
    }
    if (leds.instanceColor) leds.instanceColor.needsUpdate = true;
  });

  return (
    <group>
      <instancedMesh ref={rackRef} args={[undefined, undefined, FILLER_RACKS.length]}>
        <boxGeometry args={[RACK.width, RACK.height, RACK.depth]} />
        <meshStandardMaterial color="#15181c" metalness={0.65} roughness={0.35} />
      </instancedMesh>
      <instancedMesh ref={ledRef} args={[undefined, undefined, ledCount]}>
        <boxGeometry args={[0.04, 0.04, 0.01]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
    </group>
  );
}
