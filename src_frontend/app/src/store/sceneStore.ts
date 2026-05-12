import { create } from "zustand";
import type { SceneState } from "@/types/scene";
import { useAgentLogStore } from "@/store/agentLogStore";
import { subscribe, send } from "@/lib/websocket";
import type { WsMessage } from "@/lib/websocket";

interface SceneStore {
  state: SceneState;
  affectedService: string | null;
  autoAdvance: boolean;
  connected: boolean;
  triggerIncident: (service: string) => void;
  advancePhase: () => void;
  reset: () => void;
  setAutoAdvance: (enabled: boolean) => void;
  setPhase: (phase: SceneState, service?: string | null) => void;
  setConnected: (connected: boolean) => void;
}

export const useSceneStore = create<SceneStore>((set, get) => ({
  state: "HEALTHY",
  affectedService: null,
  autoAdvance: true,
  connected: false,

  triggerIncident: (service: string) => {
    send({ type: "trigger_incident", payload: { service } });
  },

  advancePhase: () => {
    // In backend-driven mode, phases advance automatically.
    // This is kept for DevPanel manual override if backend adds support.
  },

  reset: () => {
    send({ type: "reset_demo", payload: {} });
  },

  setAutoAdvance: (enabled: boolean) => {
    set({ autoAdvance: enabled });
    send({ type: "set_auto_advance", payload: { enabled } });
  },

  setPhase: (phase: SceneState, service?: string | null) => {
    set({
      state: phase,
      affectedService: phase === "HEALTHY" ? null : (service ?? get().affectedService),
    });
  },

  setConnected: (connected: boolean) => {
    set({ connected });
  },
}));

function handleWsMessage(message: WsMessage): void {
  const { type, payload } = message;

  if (type === "system_status") {
    const phase = (payload.phase as SceneState) || "HEALTHY";
    const affectedSvc = (payload.systems as Array<{ name: string; status: string }>)
      ?.find((s) => s.status === "degraded")?.name ?? null;
    useSceneStore.getState().setPhase(phase, affectedSvc);
    if (payload.auto_advance !== undefined) {
      useSceneStore.setState({ autoAdvance: payload.auto_advance as boolean });
    }
    useSceneStore.getState().setConnected(true);
  }

  if (type === "phase_update") {
    const phase = payload.phase as SceneState;
    useSceneStore.getState().setPhase(phase);
  }

  if (type === "incident_detected") {
    const service = payload.service as string;
    useSceneStore.getState().setPhase("INCIDENT_DETECTED", service);
  }

  if (type === "agent_log") {
    const msg = payload.message as string;
    const level = (payload.level as "info" | "warn" | "error" | "success") || "info";
    useAgentLogStore.getState().push(msg, level);
  }
}

subscribe(handleWsMessage);
