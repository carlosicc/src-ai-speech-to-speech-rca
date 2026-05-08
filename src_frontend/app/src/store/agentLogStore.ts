import { create } from "zustand";

export interface LogEntry {
  id: number;
  timestamp: string;
  message: string;
  level: "info" | "warn" | "error" | "success";
}

interface AgentLogStore {
  entries: LogEntry[];
  push: (message: string, level?: LogEntry["level"]) => void;
  clear: () => void;
}

let nextId = 1;

export const useAgentLogStore = create<AgentLogStore>((set) => ({
  entries: [],

  push: (message: string, level: LogEntry["level"] = "info") => {
    const entry: LogEntry = {
      id: nextId++,
      timestamp: new Date().toLocaleTimeString("en-GB", { hour12: false }),
      message,
      level,
    };
    set((prev) => ({
      entries: [...prev.entries.slice(-49), entry],
    }));
  },

  clear: () => {
    set({ entries: [] });
  },
}));
