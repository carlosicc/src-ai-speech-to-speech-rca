import { useEffect, useState } from "react";

type DiagramType = "architecture" | "sequence" | "database" | "voice" | "master";

const DIAGRAMS: Record<DiagramType, { label: string; file: string; icon: string }> = {
  architecture: {
    label: "Arch",
    file: "/diagrams/architectureHorizontal.html",
    icon: "\uD83C\uDFDB\uFE0F",
  },
  sequence: {
    label: "Flow",
    file: "/diagrams/sequenceDiagram.html",
    icon: "\uD83D\uDCDC",
  },
  database: {
    label: "DB Agent",
    file: "/diagrams/diagnosisAgent.html",
    icon: "\uD83E\uDE7A",
  },
  voice: {
    label: "Voice",
    file: "/diagrams/voiceAgent.html",
    icon: "\uD83D\uDCDE",
  },
  master: {
    label: "Master",
    file: "/diagrams/masterAgent.html",
    icon: "\uD83E\uDDE0",
  },
};

const BOTTOM_BUTTONS: DiagramType[] = ["architecture", "sequence", "voice"];

export function DiagramViewer() {
  const [active, setActive] = useState<DiagramType | null>(null);

  useEffect(() => {
    if (!active) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setActive(null);
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [active]);

  return (
    <>
      {/* Master Agent button — above the building, right side */}
      <button
        className="diagram-pixel-btn diagram-master-btn"
        onClick={() => setActive("master")}
        title="View Master Agent"
      >
        <span className="diagram-pixel-icon">{DIAGRAMS.master.icon}</span>
        <span className="diagram-pixel-label">{DIAGRAMS.master.label}</span>
      </button>

      {/* DB Agent button — inside Aurora DB room */}
      <button
        className="diagram-pixel-btn diagram-db-btn"
        onClick={() => setActive("database")}
        title="View Database Agent"
      >
        <span className="diagram-pixel-icon">{DIAGRAMS.database.icon}</span>
        <span className="diagram-pixel-label">{DIAGRAMS.database.label}</span>
      </button>

      {/* Bottom bar buttons */}
      <div className="diagram-overlay-buttons">
        {BOTTOM_BUTTONS.map((key) => (
          <button
            key={key}
            className="diagram-pixel-btn"
            onClick={() => setActive(key)}
            title={`View ${DIAGRAMS[key].label}`}
          >
            <span className="diagram-pixel-icon">{DIAGRAMS[key].icon}</span>
            <span className="diagram-pixel-label">{DIAGRAMS[key].label}</span>
          </button>
        ))}
      </div>

      {active && (
        <div className="diagram-overlay" onClick={() => setActive(null)}>
          <div className="diagram-modal" onClick={(e) => e.stopPropagation()}>
            <div className="diagram-modal-header">
              <div className="diagram-tabs">
                {(Object.keys(DIAGRAMS) as DiagramType[]).map((key) => (
                  <button
                    key={key}
                    className={`diagram-tab ${active === key ? "active" : ""}`}
                    onClick={() => setActive(key)}
                  >
                    {DIAGRAMS[key].icon} {DIAGRAMS[key].label}
                  </button>
                ))}
              </div>
              <button
                className="diagram-close"
                onClick={() => setActive(null)}
                aria-label="Close diagram"
              >
                &#x2715;
              </button>
            </div>
            <iframe
              className="diagram-iframe"
              src={DIAGRAMS[active].file}
              title={DIAGRAMS[active].label}
            />
          </div>
        </div>
      )}
    </>
  );
}
