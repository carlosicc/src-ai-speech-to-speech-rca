import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { CatmullRomCurve3, Group, MeshStandardMaterial, TubeGeometry, Vector3 } from "three";
import { LINK_POINTS, LINK_TARGET } from "@/datacenter/config/layout";
import { useInfrastructureStore } from "@/store/infrastructureStore";
import type { LinkStatus } from "@/types/infrastructure";

export const LINK_TARGET_NAME = "link-target";

const LINK_COLORS: Record<LinkStatus, string> = {
  connected: "#22d3ee",
  disconnecting: "#f59e0b",
  disconnected: "#ef4444",
  restoring: "#f59e0b",
};
const PULSE_COUNT = 6;
const PULSE_SPEED = 0.25;
const SPLIT_GAP = 0.35;

function tube(points: Vector3[]): TubeGeometry {
  return new TubeGeometry(new CatmullRomCurve3(points), 64, 0.035, 10, false);
}

export function ServiceLink() {
  const status = useInfrastructureStore((s) => s.link.status);
  const pulsesRef = useRef<Group>(null);

  const { curve, fullGeo, leftGeo, rightGeo, material } = useMemo(() => {
    const pts = LINK_POINTS.map((p) => new Vector3(...p));
    const mid = Math.floor(pts.length / 2);
    const left = pts.slice(0, mid + 1).map((p) => p.clone());
    const right = pts.slice(mid).map((p) => p.clone());
    left[left.length - 1].x -= SPLIT_GAP;
    left[left.length - 1].y = 0.05;
    right[0].x += SPLIT_GAP;
    right[0].y = 0.05;
    return {
      curve: new CatmullRomCurve3(pts),
      fullGeo: tube(pts),
      leftGeo: tube(left),
      rightGeo: tube(right),
      material: new MeshStandardMaterial({
        color: LINK_COLORS.connected,
        emissive: LINK_COLORS.connected,
        emissiveIntensity: 0.8,
        roughness: 0.4,
        metalness: 0.2,
      }),
    };
  }, []);

  useEffect(() => {
    material.color.set(LINK_COLORS[status]);
    material.emissive.set(LINK_COLORS[status]);
  }, [material, status]);

  useEffect(
    () => () => {
      fullGeo.dispose();
      leftGeo.dispose();
      rightGeo.dispose();
      material.dispose();
    },
    [fullGeo, leftGeo, rightGeo, material],
  );

  const connected = status === "connected";
  const pulsing = status === "disconnecting" || status === "restoring";

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    material.emissiveIntensity = pulsing ? 0.5 + Math.abs(Math.sin(t * 6)) : 0.8;
    const pulses = pulsesRef.current;
    if (!pulses) return;
    pulses.visible = connected;
    if (!connected) return;
    pulses.children.forEach((child, i) => {
      child.position.copy(curve.getPointAt((t * PULSE_SPEED + i / PULSE_COUNT) % 1));
    });
  });

  return (
    <group>
      <mesh geometry={fullGeo} material={material} visible={status !== "disconnected"} />
      <mesh geometry={leftGeo} material={material} visible={status === "disconnected"} />
      <mesh geometry={rightGeo} material={material} visible={status === "disconnected"} />

      <group ref={pulsesRef}>
        {Array.from({ length: PULSE_COUNT }, (_, i) => (
          <mesh key={i}>
            <sphereGeometry args={[0.055, 8, 8]} />
            <meshBasicMaterial color="#a5f3fc" toneMapped={false} />
          </mesh>
        ))}
      </group>

      {/* Floor service-bridge plate marking the maintenance zone */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 4.6]}>
        <planeGeometry args={[1.6, 1.0]} />
        <meshStandardMaterial color="#3b3f45" roughness={0.7} />
      </mesh>

      {/* Invisible raycast target. three.js raycasts invisible meshes, so visible={false} is fine. */}
      <mesh name={LINK_TARGET_NAME} position={LINK_TARGET.position} visible={false}>
        <boxGeometry args={LINK_TARGET.size} />
        <meshBasicMaterial />
      </mesh>
    </group>
  );
}
