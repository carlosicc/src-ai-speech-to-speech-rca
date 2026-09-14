import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/websocket", () => ({ subscribe: vi.fn(), send: vi.fn() }));

import { send } from "@/lib/websocket";
import { initialHold } from "@/datacenter/lib/holdToConfirm";
import { useDataCenterUiStore } from "@/datacenter/store/dataCenterUiStore";
import { ECS_AURORA_LINK, useInfrastructureStore } from "@/store/infrastructureStore";
import { useSceneStore } from "@/store/sceneStore";

beforeEach(() => {
  useDataCenterUiStore.setState({ mode: "director", lookingAtLink: false, hold: initialHold, panelOpen: true });
  useInfrastructureStore.setState({ link: ECS_AURORA_LINK, pendingRequestId: null, lastError: null, lastMessage: "" });
  useSceneStore.setState({ state: "HEALTHY" });
  vi.mocked(send).mockClear();
});

describe("dataCenterUiStore", () => {
  it("toggles camera mode", () => {
    useDataCenterUiStore.getState().toggleMode();
    expect(useDataCenterUiStore.getState().mode).toBe("walk");
    useDataCenterUiStore.getState().toggleMode();
    expect(useDataCenterUiStore.getState().mode).toBe("director");
  });

  it("sends exactly one break_database when a hold completes", () => {
    const s = useDataCenterUiStore.getState();
    s.holdDispatch({ type: "press" });
    for (let i = 0; i < 20; i++) s.holdDispatch({ type: "tick", dt: 0.1 });
    expect(send).toHaveBeenCalledTimes(1);
    expect(vi.mocked(send).mock.calls[0][0].type).toBe("break_database");
    expect(useDataCenterUiStore.getState().hold).toEqual(initialHold);
  });

  it("does not send when released early", () => {
    const s = useDataCenterUiStore.getState();
    s.holdDispatch({ type: "press" });
    s.holdDispatch({ type: "tick", dt: 0.5 });
    s.holdDispatch({ type: "release" });
    expect(send).not.toHaveBeenCalled();
  });
});
