import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/websocket", () => ({ subscribe: vi.fn(), send: vi.fn() }));

import { send } from "@/lib/websocket";
import { useSceneStore } from "@/store/sceneStore";
import { ECS_AURORA_LINK, canDisconnect, useInfrastructureStore } from "@/store/infrastructureStore";

beforeEach(() => {
  useInfrastructureStore.setState({
    link: ECS_AURORA_LINK,
    pendingRequestId: null,
    lastError: null,
    lastMessage: "",
  });
  useSceneStore.setState({ state: "HEALTHY" });
  vi.mocked(send).mockClear();
});

describe("requestDisconnect", () => {
  it("sends break_database with a request id and marks it pending", () => {
    const id = useInfrastructureStore.getState().requestDisconnect();
    expect(id).toBeTruthy();
    expect(useInfrastructureStore.getState().pendingRequestId).toBe(id);
    expect(send).toHaveBeenCalledWith({
      type: "break_database",
      payload: { request_id: id, source: "datacenter_3d", link_id: "ecs-aurora" },
    });
  });

  it("refuses when the phase is not HEALTHY", () => {
    useSceneStore.setState({ state: "DIAGNOSING" });
    expect(useInfrastructureStore.getState().requestDisconnect()).toBeNull();
    expect(send).not.toHaveBeenCalled();
  });

  it("refuses while a request is pending", () => {
    useInfrastructureStore.getState().requestDisconnect();
    expect(useInfrastructureStore.getState().requestDisconnect()).toBeNull();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("refuses when the link is not connected", () => {
    useInfrastructureStore.setState({ link: { ...ECS_AURORA_LINK, status: "disconnected" } });
    expect(useInfrastructureStore.getState().requestDisconnect()).toBeNull();
  });
});

describe("applyUpdate", () => {
  it("keeps the pending id on disconnecting and clears it on disconnected", () => {
    const id = useInfrastructureStore.getState().requestDisconnect()!;
    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "disconnecting", request_id: id });
    expect(useInfrastructureStore.getState().pendingRequestId).toBe(id);
    expect(useInfrastructureStore.getState().link.status).toBe("disconnecting");

    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "disconnected", request_id: id, message: "removed" });
    expect(useInfrastructureStore.getState().pendingRequestId).toBeNull();
    expect(useInfrastructureStore.getState().link.status).toBe("disconnected");
    expect(useInfrastructureStore.getState().lastMessage).toBe("removed");
  });

  it("rolls back disconnecting to connected on error and records the message", () => {
    useInfrastructureStore.getState().requestDisconnect();
    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "disconnecting" });
    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "error", message: "boom" });
    const s = useInfrastructureStore.getState();
    expect(s.link.status).toBe("connected");
    expect(s.pendingRequestId).toBeNull();
    expect(s.lastError).toBe("boom");
  });

  it("rolls back restoring to disconnected on error", () => {
    useInfrastructureStore.setState({ link: { ...ECS_AURORA_LINK, status: "restoring" } });
    useInfrastructureStore.getState().applyUpdate({ link_id: "ecs-aurora", status: "error", message: "denied" });
    expect(useInfrastructureStore.getState().link.status).toBe("disconnected");
  });

  it("ignores updates for other links", () => {
    useInfrastructureStore.getState().applyUpdate({ link_id: "other", status: "disconnected" });
    expect(useInfrastructureStore.getState().link.status).toBe("connected");
  });
});

describe("hydrate", () => {
  it("adopts the matching link from system_status and clears pending", () => {
    useInfrastructureStore.getState().requestDisconnect();
    useInfrastructureStore.getState().hydrate([{ ...ECS_AURORA_LINK, status: "disconnected" }]);
    expect(useInfrastructureStore.getState().link.status).toBe("disconnected");
    expect(useInfrastructureStore.getState().pendingRequestId).toBeNull();
  });
});

describe("canDisconnect", () => {
  it("is true only when HEALTHY, connected and idle", () => {
    expect(canDisconnect("HEALTHY", ECS_AURORA_LINK, null)).toBe(true);
    expect(canDisconnect("CALLING", ECS_AURORA_LINK, null)).toBe(false);
    expect(canDisconnect("HEALTHY", { ...ECS_AURORA_LINK, status: "restoring" }, null)).toBe(false);
    expect(canDisconnect("HEALTHY", ECS_AURORA_LINK, "req")).toBe(false);
  });
});
