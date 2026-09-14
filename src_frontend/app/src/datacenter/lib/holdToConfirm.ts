export const HOLD_DURATION_S = 1.25;

export interface HoldState {
  holding: boolean;
  /** 0..1 */
  progress: number;
}

export type HoldEvent =
  | { type: "press" }
  | { type: "release" }
  | { type: "cancel" }
  | { type: "tick"; dt: number };

export interface HoldResult {
  state: HoldState;
  confirmed: boolean;
}

export const initialHold: HoldState = { holding: false, progress: 0 };

export function reduceHold(state: HoldState, event: HoldEvent): HoldResult {
  switch (event.type) {
    case "press":
      return { state: { holding: true, progress: 0 }, confirmed: false };
    case "release":
    case "cancel":
      return { state: initialHold, confirmed: false };
    case "tick": {
      if (!state.holding) return { state, confirmed: false };
      const progress = state.progress + event.dt / HOLD_DURATION_S;
      if (progress >= 1) return { state: initialHold, confirmed: true };
      return { state: { holding: true, progress }, confirmed: false };
    }
  }
}
