import { useEffect, useRef } from "react";
import { useMetricsStore } from "@/store/metricsStore";
import { useSceneStore } from "@/store/sceneStore";
import { ROOMS } from "@/engine/config";

const BAR_WIDTH = 3;
const BAR_GAP = 1;
const SPARK_HEIGHT = 20;
const SPARK_WIDTH = (BAR_WIDTH + BAR_GAP) * 20;

function Sparkline({ data, color }: { data: number[]; color: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, SPARK_WIDTH, SPARK_HEIGHT);

    for (let i = 0; i < data.length; i++) {
      const h = (data[i] / 100) * SPARK_HEIGHT;
      ctx.fillStyle = data[i] > 80 ? "#ef5350" : color;
      ctx.fillRect(i * (BAR_WIDTH + BAR_GAP), SPARK_HEIGHT - h, BAR_WIDTH, h);
    }
  }, [data, color]);

  return (
    <canvas
      ref={canvasRef}
      width={SPARK_WIDTH}
      height={SPARK_HEIGHT}
      className="sparkline-canvas"
    />
  );
}

export function MetricsPanel() {
  const metrics = useMetricsStore((s) => s.metrics);
  const start = useMetricsStore((s) => s.start);
  const tick = useMetricsStore((s) => s.tick);
  const sceneState = useSceneStore((s) => s.state);
  const affectedService = useSceneStore((s) => s.affectedService);

  useEffect(() => {
    start(ROOMS.map((r) => r.id));
  }, [start]);

  useEffect(() => {
    const id = setInterval(() => {
      tick(sceneState, affectedService);
    }, 800);
    return () => clearInterval(id);
  }, [tick, sceneState, affectedService]);

  return (
    <section className="sidebar-section">
      <h2>LIVE METRICS</h2>
      <div className="metrics-grid">
        {ROOMS.slice(0, 4).map((room) => {
          const m = metrics[room.id];
          if (!m) return null;
          return (
            <div key={room.id} className="metrics-service">
              <span className="metrics-label">{room.id}</span>
              <div className="metrics-bars">
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">CPU</span>
                  <Sparkline data={m.cpu} color="#26c6da" />
                  <span className="metrics-bar-value">{Math.round(m.cpu[m.cpu.length - 1])}%</span>
                </div>
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">MEM</span>
                  <Sparkline data={m.mem} color="#7c4dff" />
                  <span className="metrics-bar-value">{Math.round(m.mem[m.mem.length - 1])}%</span>
                </div>
                <div className="metrics-bar-group">
                  <span className="metrics-bar-label">IOPS</span>
                  <Sparkline data={m.iops} color="#4caf50" />
                  <span className="metrics-bar-value">{Math.round(m.iops[m.iops.length - 1])}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
