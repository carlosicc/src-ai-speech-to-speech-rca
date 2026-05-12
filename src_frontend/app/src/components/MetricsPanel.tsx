import { useMetricsStore } from "@/store/metricsStore";
import { ROOMS } from "@/engine/config";

function MetricBar({ value, color }: { value: number; color: string }) {
  const barColor = value > 80 ? "#ef5350" : color;
  return (
    <div className="metric-bar-track">
      <div
        className="metric-bar-fill"
        style={{ width: `${value}%`, backgroundColor: barColor }}
      />
    </div>
  );
}

export function MetricsPanel() {
  const metrics = useMetricsStore((s) => s.metrics);

  return (
    <section className="sidebar-section">
      <h2>LIVE METRICS</h2>
      <div className="metrics-grid">
        {ROOMS.slice(0, 4).map((room) => {
          const m = metrics[room.id];
          if (!m) return null;
          const cpu = Math.round(m.cpu[m.cpu.length - 1]);
          const mem = Math.round(m.mem[m.mem.length - 1]);
          const iops = Math.round(m.iops[m.iops.length - 1]);
          return (
            <div key={room.id} className="metrics-service">
              <span className="metrics-label">{room.id}</span>
              <div className="metrics-bars">
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">CPU</span>
                  <MetricBar value={cpu} color="#26c6da" />
                  <span className="metrics-bar-value">{cpu}%</span>
                </div>
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">MEM</span>
                  <MetricBar value={mem} color="#7c4dff" />
                  <span className="metrics-bar-value">{mem}%</span>
                </div>
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">IOPS</span>
                  <MetricBar value={iops} color="#4caf50" />
                  <span className="metrics-bar-value">{iops}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
