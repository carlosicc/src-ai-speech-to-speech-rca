import { Html } from "@react-three/drei";
import { NOC_WALL } from "@/datacenter/config/layout";
import { useAgentLogStore } from "@/store/agentLogStore";
import { useSceneStore } from "@/store/sceneStore";
import { useVoiceStore } from "@/store/voiceStore";

const AGENT_LABELS: Record<string, string> = {
  master: "Master Agent",
  diagnosis: "Diagnosis Agent",
  voice: "Voice Agent",
};

export function NocWall() {
  const phase = useSceneStore((s) => s.state);
  const activeAgent = useSceneStore((s) => s.activeAgent);
  const agentStatus = useSceneStore((s) => s.agentStatus);
  const entries = useAgentLogStore((s) => s.entries);
  const transcripts = useVoiceStore((s) => s.transcripts);
  const callActive = useVoiceStore((s) => s.callActive);

  return (
    <group position={NOC_WALL.position}>
      {/* Screen housing */}
      <mesh position={[0, 0, -0.06]}>
        <boxGeometry args={[NOC_WALL.width + 0.3, NOC_WALL.height + 0.3, 0.1]} />
        <meshStandardMaterial color="#0a0c0f" metalness={0.5} roughness={0.5} />
      </mesh>
      {/* drei transform mode: 1 CSS px = 0.025 world units × scale; 1000px × 0.025 × 0.4 = 10 m. */}
      <Html transform position={[0, 0, 0.001]} scale={NOC_WALL.htmlScale} zIndexRange={[5, 0]} pointerEvents="none">
        <div className={`dc-noc dc-noc--${phase.toLowerCase()}`}>
          <div className="dc-noc-header">
            <span>AI OPERATIONS CENTER</span>
            <span className="dc-noc-phase">{phase.replace("_", " ")}</span>
          </div>
          <div className="dc-noc-body">
            <section>
              <h3>ACTIVE AGENT</h3>
              <p className="dc-noc-big">{activeAgent ? AGENT_LABELS[activeAgent] ?? activeAgent : "—"}</p>
              <p className="dc-noc-sub">{agentStatus ?? ""}</p>
            </section>
            <section>
              <h3>EVENT FEED</h3>
              {entries.slice(-6).map((e) => (
                <p key={e.id} className={`dc-log dc-log--${e.level}`}>
                  {e.timestamp} {e.message}
                </p>
              ))}
            </section>
            <section>
              <h3>VOICE {callActive ? "· LIVE" : ""}</h3>
              {transcripts.slice(-3).map((t) => (
                <p key={t.id}>
                  <strong>{t.speaker === "agent" ? "AI" : "DBA"}:</strong> {t.text}
                </p>
              ))}
            </section>
          </div>
        </div>
      </Html>
    </group>
  );
}
