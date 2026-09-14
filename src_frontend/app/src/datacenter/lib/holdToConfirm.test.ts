import { describe, expect, it } from "vitest";
import { HOLD_DURATION_S, initialHold, reduceHold } from "@/datacenter/lib/holdToConfirm";

describe("reduceHold", () => {
  it("starts holding on press with zero progress", () => {
    const { state, confirmed } = reduceHold(initialHold, { type: "press" });
    expect(state).toEqual({ holding: true, progress: 0 });
    expect(confirmed).toBe(false);
  });

  it("accumulates progress while holding", () => {
    const held = reduceHold(initialHold, { type: "press" }).state;
    const { state } = reduceHold(held, { type: "tick", dt: HOLD_DURATION_S / 2 });
    expect(state.progress).toBeCloseTo(0.5);
  });

  it("does not progress when not holding", () => {
    const { state } = reduceHold(initialHold, { type: "tick", dt: 5 });
    expect(state).toEqual(initialHold);
  });

  it("confirms once when the hold completes and resets", () => {
    const held = reduceHold(initialHold, { type: "press" }).state;
    const { state, confirmed } = reduceHold(held, { type: "tick", dt: HOLD_DURATION_S + 0.1 });
    expect(confirmed).toBe(true);
    expect(state).toEqual(initialHold);
  });

  it("release and cancel reset without confirming", () => {
    const held = reduceHold(reduceHold(initialHold, { type: "press" }).state, { type: "tick", dt: 1 }).state;
    expect(reduceHold(held, { type: "release" })).toEqual({ state: initialHold, confirmed: false });
    expect(reduceHold(held, { type: "cancel" })).toEqual({ state: initialHold, confirmed: false });
  });
});
