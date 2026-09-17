import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/websocket", () => ({ subscribe: vi.fn(), send: vi.fn() }));

import { send } from "@/lib/websocket";
import { useSceneStore } from "@/store/sceneStore";

beforeEach(() => {
  useSceneStore.setState({ state: "HEALTHY" });
  vi.mocked(send).mockClear();
});

describe("endCall", () => {
  it("sends end_call while a call is in progress", () => {
    useSceneStore.setState({ state: "CALLING" });

    useSceneStore.getState().endCall();

    expect(send).toHaveBeenCalledWith({ type: "end_call", payload: {} });
  });

  it.each(["HEALTHY", "INCIDENT_DETECTED", "DIAGNOSING", "RECOVERING", "RESOLVED"] as const)(
    "refuses outside the CALLING phase (%s)",
    (phase) => {
      useSceneStore.setState({ state: phase });

      useSceneStore.getState().endCall();

      expect(send).not.toHaveBeenCalled();
    },
  );
});
