import { useState, useEffect } from "react";
import { useSceneStore } from "@/store/sceneStore";
import { useVoiceStore } from "@/store/voiceStore";
import { send } from "@/lib/websocket";
import { startAudioCapture, stopAudioCapture } from "@/lib/audioHandler";
import { ROOMS } from "@/engine/config";

const VOICE_MODE_TOOLTIPS: Record<string, string> = {
  mode_a: "AgentCore + Twilio (managed agent, real phone call)",
  mode_b: "Bedrock + Twilio (direct stream, real phone call)",
  mode_c: "Bedrock + Browser (mic/speaker, no phone)",
};

export function DevPanel() {
  const [visible, setVisible] = useState(false);
  const state = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);
  const triggerIncident = useSceneStore((s) => s.triggerIncident);
  const reset = useSceneStore((s) => s.reset);
  const autoAdvance = useSceneStore((s) => s.autoAdvance);
  const setAutoAdvance = useSceneStore((s) => s.setAutoAdvance);
  const connected = useSceneStore((s) => s.connected);

  const [voiceMode, setVoiceMode] = useState("mode_b");
  const [phoneNumber, setPhoneNumber] = useState("+44XXXXXXXXXX");
  const [micActive, setMicActive] = useState(false);
  const callActive = useVoiceStore((s) => s.callActive);
  const transcripts = useVoiceStore((s) => s.transcripts);

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

  const handleVoiceModeChange = (mode: string) => {
    if (micActive) {
      stopAudioCapture();
      setMicActive(false);
      send({ type: "stop_voice", payload: {} });
    }
    setVoiceMode(mode);
    send({ type: "set_voice_mode", payload: { mode } });
  };

  const handlePhoneSubmit = () => {
    send({ type: "set_phone_number", payload: { phone_number: phoneNumber } });
  };

  const handleMicToggle = async () => {
    if (micActive) {
      stopAudioCapture();
      setMicActive(false);
      send({ type: "stop_voice", payload: {} });
    } else {
      try {
        await startAudioCapture();
        setMicActive(true);
      } catch (err) {
        console.error("Failed to start audio capture:", err);
      }
    }
  };

  const micDisabled = voiceMode !== "mode_c" || (state !== "CALLING" && !micActive);

  return (
    <>
      <button
        className="dev-panel-toggle"
        onClick={() => setVisible((v) => !v)}
        title="Toggle DevPanel (Ctrl+D)"
        aria-label="Toggle DevPanel"
      >
        &#x2699;
      </button>
      {visible && (
        <div className="dev-panel">
          <div className="dev-panel-header">
            <span>DEV PANEL</span>
            <span className={`dev-panel-status ${connected ? "connected" : "disconnected"}`}>
              {connected ? "WS LIVE" : "WS OFF"}
            </span>
            <button onClick={() => setVisible(false)}>&#x2715;</button>
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
                  title={`Manually start an incident on ${r.label}`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          <div className="dev-panel-section">
            <label>CONTROL:</label>
            <div className="dev-panel-buttons">
              <button onClick={reset} title="Stop current incident, return to HEALTHY">
                Reset
              </button>
              <button
                onClick={() => setAutoAdvance(!autoAdvance)}
                title="Auto-trigger incidents every 3min for booth passersby"
                className={autoAdvance ? "active" : ""}
              >
                Auto: {autoAdvance ? "ON" : "OFF"}
              </button>
            </div>
          </div>
          <div className="dev-panel-section">
            <label>AWS OPERATIONS:</label>
            <div className="dev-panel-buttons">
              <button
                onClick={() => send({ type: "break_database", payload: {} })}
                disabled={state !== "HEALTHY"}
                title="Stop RDS Aurora cluster via AWS API (real StopDBCluster call)"
              >
                Break DB
              </button>
            </div>
          </div>
          <div className="dev-panel-section">
            <label>VOICE MODE:</label>
            <div className="dev-panel-buttons">
              {(["mode_a", "mode_b", "mode_c"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => handleVoiceModeChange(mode)}
                  className={voiceMode === mode ? "active" : ""}
                  title={VOICE_MODE_TOOLTIPS[mode]}
                >
                  {mode.replace("_", " ").toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div className="dev-panel-section">
            <label>PHONE:</label>
            <div className="dev-panel-inline">
              <input
                type="tel"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                placeholder="+44..."
              />
              <button onClick={handlePhoneSubmit} title="Send phone number to backend for Twilio calls">
                Set
              </button>
            </div>
          </div>
          <div className="dev-panel-section">
            <label>VOICE (MODE C):</label>
            <div className="dev-panel-buttons">
              <button
                onClick={handleMicToggle}
                className={micActive ? "active" : ""}
                disabled={micDisabled}
                title="Activate browser microphone for voice conversation (Mode C only)"
              >
                {micActive ? "Stop Mic" : "Start Mic"}
              </button>
              <span className={`dev-panel-status ${callActive ? "connected" : "disconnected"}`}>
                {callActive ? "CALL ACTIVE" : "NO CALL"}
              </span>
            </div>
            {transcripts.length > 0 && (
              <div className="dev-panel-transcripts">
                {transcripts.slice(-5).map((t) => (
                  <div key={t.id} className={`transcript-line transcript-${t.speaker}`}>
                    <strong>{t.speaker === "agent" ? "AI" : "You"}:</strong> {t.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
