import { Html } from "@react-three/drei";
import { RACK, type HeroRack as HeroRackConfig } from "@/datacenter/config/layout";
import { useInfrastructureStore } from "@/store/infrastructureStore";
import { useMetricsStore } from "@/store/metricsStore";
import { useSceneStore } from "@/store/sceneStore";

type RackHealth = "healthy" | "alert" | "recovering";

const PANEL_COLORS: Record<RackHealth, string> = {
  healthy: "#16a34a",
  alert: "#dc2626",
  recovering: "#f59e0b",
};

function useRackHealth(id: string): RackHealth {
  const phase = useSceneStore((s) => s.state);
  const affected = useSceneStore((s) => s.affectedService);
  if (affected !== id || phase === "HEALTHY") return "healthy";
  if (phase === "RECOVERING" || phase === "RESOLVED") return "recovering";
  return "alert";
}

function last(values: number[] | undefined): number {
  return values && values.length > 0 ? Math.round(values[values.length - 1]) : 0;
}

const RULE_TEXT: Record<string, string> = {
  connected: "ALLOW ECS_SG → RDS_SG TCP/3306",
  disconnecting: "REVOKING RULE…",
  disconnected: "RULE MISSING",
  restoring: "RESTORING RULE…",
};

export function HeroRack({ rack }: { rack: HeroRackConfig }) {
  const health = useRackHealth(rack.id);
  const metrics = useMetricsStore((s) => s.metrics[rack.id]);
  const linkStatus = useInfrastructureStore((s) => s.link.status);

  return (
    <group position={[rack.x, 0, rack.z]}>
      <mesh position={[0, RACK.height / 2, 0]}>
        <boxGeometry args={[RACK.width, RACK.height, RACK.depth]} />
        <meshStandardMaterial color="#1a1e23" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* Front status panel */}
      <mesh position={[0, 1.2, RACK.depth / 2 + 0.006]}>
        <planeGeometry args={[0.6, 1.6]} />
        <meshStandardMaterial
          color="#0b0d10"
          emissive={PANEL_COLORS[health]}
          emissiveIntensity={health === "healthy" ? 0.35 : 1.2}
        />
      </mesh>
      <Html
        position={[0, RACK.height + 0.45, RACK.depth / 2]}
        center
        distanceFactor={7}
        zIndexRange={[10, 0]}
        style={{ pointerEvents: "none" }}
      >
        <div className={`dc-rack-label dc-rack-label--${health}`}>
          <div className="dc-rack-title">{rack.label}</div>
          <div className="dc-rack-metrics">
            {rack.id === "network"
              ? RULE_TEXT[linkStatus]
              : `CPU ${last(metrics?.cpu)}% · MEM ${last(metrics?.mem)}% · IOPS ${last(metrics?.iops)}`}
          </div>
          <div className="dc-rack-status">{health.toUpperCase()}</div>
        </div>
      </Html>
    </group>
  );
}
