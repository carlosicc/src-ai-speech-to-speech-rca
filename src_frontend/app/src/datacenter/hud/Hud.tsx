import { AgentLog } from "@/components/AgentLog";
import { MetricsPanel } from "@/components/MetricsPanel";
import { useDataCenterUiStore } from "@/datacenter/store/dataCenterUiStore";
import { canDisconnect, useInfrastructureStore } from "@/store/infrastructureStore";
import { useSceneStore } from "@/store/sceneStore";
import { useVoiceStore } from "@/store/voiceStore";

const AGENT_LABELS: Record<string, string> = {
  master: "Master Agent",
  diagnosis: "Diagnosis Agent",
  voice: "Voice Agent",
};

export function Hud() {
  const phase = useSceneStore((s) => s.state);
  const connected = useSceneStore((s) => s.connected);
  const activeAgent = useSceneStore((s) => s.activeAgent);
  const reset = useSceneStore((s) => s.reset);

  const link = useInfrastructureStore((s) => s.link);
  const pendingRequestId = useInfrastructureStore((s) => s.pendingRequestId);
  const lastError = useInfrastructureStore((s) => s.lastError);
  const clearError = useInfrastructureStore((s) => s.clearError);

  const mode = useDataCenterUiStore((s) => s.mode);
  const toggleMode = useDataCenterUiStore((s) => s.toggleMode);
  const lookingAtLink = useDataCenterUiStore((s) => s.lookingAtLink);
  const hold = useDataCenterUiStore((s) => s.hold);
  const holdDispatch = useDataCenterUiStore((s) => s.holdDispatch);
  const panelOpen = useDataCenterUiStore((s) => s.panelOpen);
  const togglePanel = useDataCenterUiStore((s) => s.togglePanel);

  const transcripts = useVoiceStore((s) => s.transcripts);
  const callActive = useVoiceStore((s) => s.callActive);

  const allowed = canDisconnect(phase, link, pendingRequestId);
  const buttonAllowed = allowed && (mode === "director" || lookingAtLink);
  const progressPct = Math.round(hold.progress * 100);

  return (
    <div className="dc-hud">
      <header className="dc-topbar">
        <span className="dc-title">AI OPERATIONS CENTER · DATA CENTER TWIN</span>
        <span className={`dc-pill ${connected ? "dc-pill--ok" : "dc-pill--bad"}`}>{connected ? "WS LIVE" : "WS OFF"}</span>
        <span className={`dc-pill dc-pill--phase-${phase.toLowerCase()}`}>{phase.replace("_", " ")}</span>
        <span className="dc-pill">{activeAgent ? AGENT_LABELS[activeAgent] ?? activeAgent : "Agents idle"}</span>
        <span className={`dc-pill dc-pill--link-${link.status}`}>ECS→AURORA {link.status.toUpperCase()}</span>
      </header>

      {mode === "walk" && (
        <div className={`dc-reticle ${lookingAtLink ? "dc-reticle--active" : ""}`}>
          {lookingAtLink && (
            <div className="dc-prompt">
              <div>ECS → AURORA APPLICATION LINK · TCP/3306</div>
              <div>
                {allowed
                  ? "Hold E to disconnect — this triggers a real demo incident"
                  : phase === "HEALTHY"
                    ? "Link down — press RESET to restore the rule"
                    : "Link locked during incident"}
              </div>
              {hold.holding && <div className="dc-progress"><div style={{ width: `${progressPct}%` }} /></div>}
            </div>
          )}
        </div>
      )}

      <div className="dc-help">
        <span>V walk/director</span>
        <span>↑↓←→ move</span>
        <span>G go to link</span>
        <span>hold E disconnect</span>
        <span>R respawn</span>
        <span>Ctrl+D dev panel</span>
      </div>

      <aside className={`dc-panel ${panelOpen ? "" : "dc-panel--closed"}`}>
        <button className="dc-panel-toggle" onClick={togglePanel} aria-label="Toggle operations panel">
          {panelOpen ? "›" : "‹"}
        </button>
        {panelOpen && (
          <div className="dc-panel-body">
            <MetricsPanel />
            <AgentLog />
            <section className="sidebar-section">
              <h2>VOICE {callActive ? "· LIVE" : ""}</h2>
              {transcripts.slice(-4).map((t) => (
                <p key={t.id} className={`dc-transcript dc-transcript--${t.speaker}`}>
                  <strong>{t.speaker === "agent" ? "AI" : "DBA"}:</strong> {t.text}
                </p>
              ))}
            </section>
          </div>
        )}
      </aside>

      <footer className="dc-presenter">
        <button
          className={`dc-btn dc-btn--danger ${hold.holding ? "dc-btn--holding" : ""}`}
          disabled={!buttonAllowed}
          onPointerDown={(e) => {
            if (e.button !== 0 || !buttonAllowed) return;
            holdDispatch({ type: "press" });
          }}
          onPointerUp={() => holdDispatch({ type: "release" })}
          onPointerLeave={() => holdDispatch({ type: "release" })}
          onPointerCancel={() => holdDispatch({ type: "release" })}
          title={
            mode === "walk" && !lookingAtLink
              ? "In walk mode, face the service bridge (G) first"
              : "Hold for 1.25 s to remove the real security-group rule"
          }
        >
          {hold.holding ? `DISCONNECTING… ${progressPct}%` : "HOLD TO DISCONNECT LINK"}
        </button>
        <button className="dc-btn" onClick={reset} title="Stop incident, restore rule, return to HEALTHY">RESET</button>
        <button className="dc-btn" onClick={toggleMode}>{mode === "director" ? "WALK MODE" : "DIRECTOR MODE"}</button>
        <a className="dc-btn" href="/">CLASSIC UI</a>
      </footer>

      {lastError && (
        <div className="dc-toast" role="alert">
          <span>AWS operation failed: {lastError}</span>
          <button onClick={clearError} aria-label="Dismiss">✕</button>
        </div>
      )}
    </div>
  );
}
