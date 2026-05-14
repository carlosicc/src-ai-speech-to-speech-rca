import { create } from "zustand";
import { subscribe } from "@/lib/websocket";
import type { WsMessage } from "@/lib/websocket";

export interface ServiceMetrics {
  cpu: number[];
  mem: number[];
  iops: number[];
}

interface MetricsStore {
  metrics: Record<string, ServiceMetrics>;
  updateService: (service: string, cpu: number, mem: number, iops: number) => void;
}

const HISTORY_LENGTH = 20;

export const useMetricsStore = create<MetricsStore>((set) => ({
  metrics: {},

  updateService: (service: string, cpu: number, mem: number, iops: number) => {
    set((prev) => {
      const existing = prev.metrics[service] || {
        cpu: Array(HISTORY_LENGTH).fill(0),
        mem: Array(HISTORY_LENGTH).fill(0),
        iops: Array(HISTORY_LENGTH).fill(0),
      };
      return {
        metrics: {
          ...prev.metrics,
          [service]: {
            cpu: [...existing.cpu.slice(1), cpu],
            mem: [...existing.mem.slice(1), mem],
            iops: [...existing.iops.slice(1), iops],
          },
        },
      };
    });
  },
}));

function handleWsMessage(message: WsMessage): void {
  if (!message.payload) return;
  if (message.type === "metrics_update") {
    const { service, cpu, mem, iops } = message.payload as {
      service: string;
      cpu: number;
      mem: number;
      iops: number;
    };
    useMetricsStore.getState().updateService(service, cpu, mem, iops);
  }
}

subscribe(handleWsMessage);
