// src_frontend/app/src/store/metricsStore.ts
import { create } from "zustand";
import type { SceneState } from "@/types/scene";

export interface ServiceMetrics {
  cpu: number[];
  mem: number[];
  iops: number[];
}

interface MetricsStore {
  metrics: Record<string, ServiceMetrics>;
  start: (serviceIds: string[]) => void;
  stop: () => void;
  tick: (state: SceneState, affectedService: string | null) => void;
}

const HISTORY_LENGTH = 20;

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

function fluctuate(current: number, base: number, variance: number): number {
  const drift = (Math.random() - 0.5) * variance;
  const pull = (base - current) * 0.1;
  return clamp(current + drift + pull, 0, 100);
}

function spike(current: number): number {
  return clamp(current + (Math.random() * 15 + 10), 0, 100);
}

function drop(current: number): number {
  return clamp(current - (Math.random() * 10 + 5), 0, 100);
}

let intervalId: ReturnType<typeof setInterval> | null = null;

export const useMetricsStore = create<MetricsStore>((set) => ({
  metrics: {},

  start: (serviceIds: string[]) => {
    const initial: Record<string, ServiceMetrics> = {};
    for (const id of serviceIds) {
      initial[id] = {
        cpu: Array(HISTORY_LENGTH).fill(30 + Math.random() * 20),
        mem: Array(HISTORY_LENGTH).fill(40 + Math.random() * 15),
        iops: Array(HISTORY_LENGTH).fill(20 + Math.random() * 10),
      };
    }
    set({ metrics: initial });
  },

  stop: () => {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
  },

  tick: (state: SceneState, affectedService: string | null) => {
    set((prev) => {
      const next: Record<string, ServiceMetrics> = {};
      for (const [id, m] of Object.entries(prev.metrics)) {
        const isAffected = id === affectedService;
        const isIncident = state !== "HEALTHY" && state !== "RESOLVED";

        let cpu: number, mem: number, iops: number;
        const lastCpu = m.cpu[m.cpu.length - 1];
        const lastMem = m.mem[m.mem.length - 1];
        const lastIops = m.iops[m.iops.length - 1];

        if (isAffected && isIncident) {
          cpu = spike(lastCpu);
          mem = spike(lastMem);
          iops = drop(lastIops);
        } else {
          cpu = fluctuate(lastCpu, 35, 6);
          mem = fluctuate(lastMem, 45, 4);
          iops = fluctuate(lastIops, 25, 5);
        }

        next[id] = {
          cpu: [...m.cpu.slice(1), cpu],
          mem: [...m.mem.slice(1), mem],
          iops: [...m.iops.slice(1), iops],
        };
      }
      return { metrics: next };
    });
  },
}));
