import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { PointLight } from "three";
import { ROOM } from "@/datacenter/config/layout";
import { useSceneStore } from "@/store/sceneStore";

const HALF_W = ROOM.width / 2;
const HALF_D = ROOM.depth / 2;
const CEILING_LIGHT_Z = [-16, -8, 0, 8, 16];
const WALL_COLOR = "#23272c";

export function Facility() {
  const phase = useSceneStore((s) => s.state);
  const alarmRef = useRef<PointLight>(null);

  const alarm = phase === "INCIDENT_DETECTED" || phase === "DIAGNOSING" || phase === "CALLING";
  const amber = phase === "RECOVERING";

  useFrame(({ clock }) => {
    const light = alarmRef.current;
    if (!light) return;
    if (alarm) light.intensity = 40 + Math.sin(clock.elapsedTime * 6) * 35;
    else if (amber) light.intensity = 25;
    else light.intensity = 0;
  });

  return (
    <group>
      <color attach="background" args={["#07090c"]} />
      <fog attach="fog" args={["#07090c", 6, 48]} />
      <ambientLight intensity={0.35} />
      {CEILING_LIGHT_Z.map((z) => (
        <pointLight
          key={z}
          position={[0, ROOM.height - 0.2, z]}
          intensity={alarm ? 60 : 140}
          distance={26}
          decay={2}
          color={alarm ? "#ffb4a8" : "#dfe8ff"}
        />
      ))}
      {/* Alarm strobe above the hero row */}
      <pointLight
        ref={alarmRef}
        position={[0, 3.6, 3]}
        distance={20}
        decay={2}
        color={amber ? "#ffb300" : "#ff1f1f"}
        intensity={0}
      />

      {/* Floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[ROOM.width, ROOM.depth]} />
        <meshStandardMaterial color="#1c1f23" roughness={0.85} metalness={0.15} />
      </mesh>
      {/* Safety stripes marking the hero aisle */}
      {[4.9, 7.1].map((z) => (
        <mesh key={z} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, z]}>
          <planeGeometry args={[14, 0.08]} />
          <meshStandardMaterial color="#e6b400" roughness={0.6} />
        </mesh>
      ))}

      {/* Ceiling */}
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, ROOM.height, 0]}>
        <planeGeometry args={[ROOM.width, ROOM.depth]} />
        <meshStandardMaterial color="#0d1014" roughness={1} />
      </mesh>

      {/* Walls */}
      <mesh position={[0, ROOM.height / 2, -HALF_D]}>
        <boxGeometry args={[ROOM.width, ROOM.height, 0.2]} />
        <meshStandardMaterial color={WALL_COLOR} roughness={0.9} />
      </mesh>
      <mesh position={[0, ROOM.height / 2, HALF_D]}>
        <boxGeometry args={[ROOM.width, ROOM.height, 0.2]} />
        <meshStandardMaterial color={WALL_COLOR} roughness={0.9} />
      </mesh>
      <mesh position={[-HALF_W, ROOM.height / 2, 0]}>
        <boxGeometry args={[0.2, ROOM.height, ROOM.depth]} />
        <meshStandardMaterial color={WALL_COLOR} roughness={0.9} />
      </mesh>
      <mesh position={[HALF_W, ROOM.height / 2, 0]}>
        <boxGeometry args={[0.2, ROOM.height, ROOM.depth]} />
        <meshStandardMaterial color={WALL_COLOR} roughness={0.9} />
      </mesh>
    </group>
  );
}
