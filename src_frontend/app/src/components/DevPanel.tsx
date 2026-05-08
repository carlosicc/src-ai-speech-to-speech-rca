import { useState, useEffect } from "react";
import { useSceneStore } from "@/store/sceneStore";
import { ROOMS } from "@/engine/config";

export function DevPanel() {
  const [visible, setVisible] = useState(false);
  const state = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);
  const triggerIncident = useSceneStore((s) => s.triggerIncident);
  const advancePhase = useSceneStore((s) => s.advancePhase);
  const reset = useSceneStore((s) => s.reset);
  const autoAdvance = useSceneStore((s) => s.autoAdvance);
  const setAutoAdvance = useSceneStore((s) => s.setAutoAdvance);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "d") {
        e.preventDefault();
        setVisible((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (!visible) return null;

  return (
    <div className="dev-panel">
      <div className="dev-panel-header">
        <span>DEV PANEL</span>
        <button onClick={() => setVisible(false)}>✕</button>
      </div>
      <div className="dev-panel-state">
        State: <strong>{state}</strong>
        {affectedService && <> | Room: <strong>{affectedService}</strong></>}
      </div>
      <div className="dev-panel-section">
        <label>TRIGGER INCIDENT:</label>
        <div className="dev-panel-buttons">
          {ROOMS.map((r) => (
            <button
              key={r.id}
              onClick={() => triggerIncident(r.id)}
              disabled={state !== "HEALTHY"}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="dev-panel-section">
        <label>CONTROL:</label>
        <div className="dev-panel-buttons">
          <button onClick={advancePhase}>Advance Phase →</button>
          <button onClick={reset}>Reset</button>
          <button onClick={() => setAutoAdvance(!autoAdvance)}>
            Auto: {autoAdvance ? "ON" : "OFF"}
          </button>
        </div>
      </div>
    </div>
  );
}
