import { useState } from "react";

type DiagramType = "architecture" | "sequence";

const DIAGRAMS: Record<DiagramType, { label: string; file: string; icon: string }> = {
  architecture: {
    label: "Architecture",
    file: "/diagrams/architectureHorizontal.html",
    icon: "\u2B1A",
  },
  sequence: {
    label: "Sequence",
    file: "/diagrams/sequenceDiagram.html",
    icon: "\u21C6",
  },
};

export function DiagramViewer() {
  const [active, setActive] = useState<DiagramType | null>(null);

  return (
    <>
      <div className="diagram-buttons">
        <button
          className="diagram-btn"
          onClick={() => setActive("architecture")}
          title="View Architecture Diagram"
          aria-label="View Architecture Diagram"
        >
          {DIAGRAMS.architecture.icon}
        </button>
        <button
          className="diagram-btn"
          onClick={() => setActive("sequence")}
          title="View Sequence Diagram"
          aria-label="View Sequence Diagram"
        >
          {DIAGRAMS.sequence.icon}
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
