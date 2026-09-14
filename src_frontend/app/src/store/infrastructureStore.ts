import { create } from "zustand";
import { subscribe, send } from "@/lib/websocket";
import type { WsMessage } from "@/lib/websocket";
import { useSceneStore } from "@/store/sceneStore";
import type { InfrastructureLink, LinkStatus, LinkUpdatePayload } from "@/types/infrastructure";
import type { SceneState } from "@/types/scene";

export const ECS_AURORA_LINK: InfrastructureLink = {
  id: "ecs-aurora",
  source: "ecs-cluster",
  target: "aurora-db",
  protocol: "tcp",
  port: 3306,
  status: "connected",
};

const ROLLBACK: Partial<Record<LinkStatus, LinkStatus>> = {
  disconnecting: "connected",
  restoring: "disconnected",
};

export function canDisconnect(phase: SceneState, link: InfrastructureLink, pendingRequestId: string | null): boolean {
  return phase === "HEALTHY" && link.status === "connected" && pendingRequestId === null;
}

interface InfrastructureStore {
  link: InfrastructureLink;
  pendingRequestId: string | null;
  lastError: string | null;
  lastMessage: string;
  requestDisconnect: () => string | null;
  applyUpdate: (payload: LinkUpdatePayload) => void;
  hydrate: (links: InfrastructureLink[]) => void;
  clearError: () => void;
}

export const useInfrastructureStore = create<InfrastructureStore>((set, get) => ({
  link: ECS_AURORA_LINK,
  pendingRequestId: null,
  lastError: null,
  lastMessage: "",

  requestDisconnect: () => {
    const { link, pendingRequestId } = get();
    if (!canDisconnect(useSceneStore.getState().state, link, pendingRequestId)) return null;
    const requestId = crypto.randomUUID();
    set({ pendingRequestId: requestId, lastError: null });
    send({
      type: "break_database",
      payload: { request_id: requestId, source: "datacenter_3d", link_id: link.id },
    });
    return requestId;
  },

  applyUpdate: (payload) => {
    const { link, pendingRequestId } = get();
    if (payload.link_id !== link.id) return;
    if (payload.status === "error") {
      set({
        link: { ...link, status: ROLLBACK[link.status] ?? link.status },
        pendingRequestId: null,
        lastError: payload.message ?? "AWS operation failed",
      });
      return;
    }
    set({
      link: { ...link, status: payload.status },
      lastMessage: payload.message ?? "",
      pendingRequestId: payload.status === "disconnecting" ? pendingRequestId : null,
    });
  },

  hydrate: (links) => {
    const match = links.find((l) => l.id === get().link.id);
    if (match) set({ link: match, pendingRequestId: null });
  },

  clearError: () => set({ lastError: null }),
}));

function handleWsMessage(message: WsMessage): void {
  const { type, payload } = message;
  if (!payload) return;
  if (type === "infrastructure_link_update") {
    useInfrastructureStore.getState().applyUpdate(payload as unknown as LinkUpdatePayload);
  }
  if (type === "system_status" && Array.isArray(payload.infrastructure_links)) {
    useInfrastructureStore.getState().hydrate(payload.infrastructure_links as InfrastructureLink[]);
  }
}

subscribe(handleWsMessage);
