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

const AGENT_LABELS: Record<string, string> = {
  master: "Master Agent",
  diagnosis: "Diagnosis Agent",
  voice: "Voice Agent",
};

export function Sidebar() {
  const state = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);
  const activeAgent = useSceneStore((s) => s.activeAgent);
  const agentStatus = useSceneStore((s) => s.agentStatus);

  const isActive = state !== "HEALTHY";

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1 className="sidebar-title">AI OPERATIONS CENTER</h1>
        <img src="/pace-logo.png" alt="PACE" className="pace-logo" />
      </div>

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

        {isActive && (
          <div className="agent-roster">
            {(["master", "diagnosis", "voice"] as const).map((agent) => {
              const isCurrent = activeAgent === agent;
              return (
                <div key={agent} className={`agent-chip${isCurrent ? " agent-chip--active" : ""}`}>
                  <span className={`agent-chip-dot${isCurrent ? " agent-chip-dot--active" : ""}`} />
                  <span className="agent-chip-label">{AGENT_LABELS[agent]}</span>
                  {isCurrent && agentStatus && (
                    <span className="agent-chip-status">{agentStatus}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <AgentLog />
    </div>
  );
}
