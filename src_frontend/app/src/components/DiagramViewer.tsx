import { useState } from "react";

type DiagramType = "architecture" | "sequence";

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
};

export function DiagramViewer() {
  const [active, setActive] = useState<DiagramType | null>(null);

  return (
    <>
      <div className="diagram-overlay-buttons">
        <button
          className="diagram-pixel-btn"
          onClick={() => setActive("architecture")}
          title="View Architecture Diagram"
        >
          <span className="diagram-pixel-icon">{DIAGRAMS.architecture.icon}</span>
          <span className="diagram-pixel-label">{DIAGRAMS.architecture.label}</span>
        </button>
        <button
          className="diagram-pixel-btn"
          onClick={() => setActive("sequence")}
          title="View Sequence Diagram"
        >
          <span className="diagram-pixel-icon">{DIAGRAMS.sequence.icon}</span>
          <span className="diagram-pixel-label">{DIAGRAMS.sequence.label}</span>
        </button>
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
