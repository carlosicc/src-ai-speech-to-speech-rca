import { useSceneStore } from "@/store/sceneStore";
import { ROOMS } from "@/engine/config";
import type { SceneState } from "@/types/scene";
import { MetricsPanel } from "@/components/MetricsPanel";
import { AgentLog } from "@/components/AgentLog";

const AGENT_MESSAGES: Record<SceneState, string> = {
  HEALTHY: "Monitoring system activity. No issues detected.",
  INCIDENT_DETECTED: "⚠ ALERT — Anomaly detected. Activating diagnosis protocol...",
  DIAGNOSING: "Running health checks, pulling logs, analyzing root cause...",
  CALLING: "Escalating to on-call DBA. Initiating voice call...",
  RECOVERING: "Recovery procedure in progress. Monitoring restoration...",
  RESOLVED: "✓ Incident resolved. All systems nominal.",
};

export function Sidebar() {
  const state = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);

  const isActive = state !== "HEALTHY";

  return (
    <div className="sidebar">
      <h1 className="sidebar-title">AI OPERATIONS CENTER</h1>

      <section className="sidebar-section">
        <h2>SYSTEMS OVERVIEW</h2>
        <ul className="system-list">
          {ROOMS.map((r) => {
            const isAffected = affectedService === r.id;
            return (
              <li key={r.id} className={`system-item${isAffected ? " system-item--alert" : ""}`}>
                <span
                  className={`status-dot${isAffected ? " status-dot--alert" : ""}`}
                  style={{
                    backgroundColor: isAffected ? "#ef5350" : "#4caf50",
                  }}
                />
                <span className="system-label">{r.label}</span>
                <span className="system-status">
                  {isAffected ? "ALERT" : "HEALTHY"}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      <MetricsPanel />

      <section className="sidebar-section">
        <h2>AI AGENT STATUS</h2>
        <div className="agent-status">
          <span className={`agent-indicator${isActive ? " agent-indicator--active" : ""}`} />
          <span>{isActive ? state.replace("_", " ") : "Idle"}</span>
        </div>
        <p className="agent-message">{AGENT_MESSAGES[state]}</p>
      </section>

      <AgentLog />
    </div>
  );
}
