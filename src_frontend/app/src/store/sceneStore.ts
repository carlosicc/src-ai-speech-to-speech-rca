import { create } from "zustand";
import type { SceneState } from "@/types/scene";

interface SceneStore {
  state: SceneState;
  affectedService: string | null;
  autoAdvance: boolean;
  triggerIncident: (service: string) => void;
  advancePhase: () => void;
  reset: () => void;
  setAutoAdvance: (enabled: boolean) => void;
}

const STATE_ORDER: SceneState[] = [
  "HEALTHY",
  "INCIDENT_DETECTED",
  "DIAGNOSING",
  "CALLING",
  "RECOVERING",
  "RESOLVED",
];

const PHASE_DURATIONS: Record<SceneState, number> = {
  HEALTHY: 0,
  INCIDENT_DETECTED: 3000,
  DIAGNOSING: 4000,
  CALLING: 5000,
  RECOVERING: 3000,
  RESOLVED: 2000,
};

let autoTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleNext(get: () => SceneStore) {
  if (autoTimer) clearTimeout(autoTimer);
  const { state, autoAdvance } = get();
  if (!autoAdvance || state === "HEALTHY") return;

  const duration = PHASE_DURATIONS[state];
  if (duration <= 0) return;

  autoTimer = setTimeout(() => {
    const store = get();
    if (store.autoAdvance) {
      store.advancePhase();
    }
  }, duration);
}

export const useSceneStore = create<SceneStore>((set, get) => ({
  state: "HEALTHY",
  affectedService: null,
  autoAdvance: true,
  triggerIncident: (service: string) => {
    set({ state: "INCIDENT_DETECTED", affectedService: service });
    scheduleNext(get);
  },
  advancePhase: () => {
    const current = STATE_ORDER.indexOf(get().state);
    const next = STATE_ORDER[(current + 1) % STATE_ORDER.length];
    set({
      state: next,
      affectedService: next === "HEALTHY" ? null : get().affectedService,
    });
    scheduleNext(get);
  },
  reset: () => {
    if (autoTimer) clearTimeout(autoTimer);
    set({ state: "HEALTHY", affectedService: null });
  },
  setAutoAdvance: (enabled: boolean) => {
    set({ autoAdvance: enabled });
    if (enabled) scheduleNext(get);
    else if (autoTimer) clearTimeout(autoTimer);
  },
}));
