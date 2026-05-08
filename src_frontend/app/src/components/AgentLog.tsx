import { useEffect, useRef } from "react";
import { useAgentLogStore } from "@/store/agentLogStore";

const LEVEL_COLORS: Record<string, string> = {
  info: "#9e9e9e",
  warn: "#ffa726",
  error: "#ef5350",
  success: "#4caf50",
};

export function AgentLog() {
  const entries = useAgentLogStore((s) => s.entries);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries]);

  return (
    <section className="sidebar-section">
      <h2>AI AGENT LOG</h2>
      <div className="agent-log" ref={scrollRef}>
        {entries.length === 0 && (
          <p className="agent-log-empty">No activity yet.</p>
        )}
        {entries.map((e) => (
          <div key={e.id} className="agent-log-entry">
            <span className="agent-log-time">{e.timestamp}</span>
            <span
              className="agent-log-msg"
              style={{ color: LEVEL_COLORS[e.level] }}
            >
              {e.message}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
