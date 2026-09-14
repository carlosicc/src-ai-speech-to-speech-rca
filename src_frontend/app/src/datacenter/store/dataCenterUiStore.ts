import { create } from "zustand";
import { initialHold, reduceHold, type HoldEvent, type HoldState } from "@/datacenter/lib/holdToConfirm";
import { useInfrastructureStore } from "@/store/infrastructureStore";

export type CameraMode = "director" | "walk";

interface DataCenterUiStore {
  mode: CameraMode;
  lookingAtLink: boolean;
  hold: HoldState;
  panelOpen: boolean;
  setMode: (mode: CameraMode) => void;
  toggleMode: () => void;
  setLookingAtLink: (looking: boolean) => void;
  togglePanel: () => void;
  holdDispatch: (event: HoldEvent) => void;
}

export const useDataCenterUiStore = create<DataCenterUiStore>((set, get) => ({
  mode: "director",
  lookingAtLink: false,
  hold: initialHold,
  panelOpen: true,

  setMode: (mode) => set({ mode }),
  toggleMode: () => set({ mode: get().mode === "director" ? "walk" : "director" }),
  setLookingAtLink: (looking) => set({ lookingAtLink: looking }),
  togglePanel: () => set({ panelOpen: !get().panelOpen }),

  holdDispatch: (event) => {
    const { state, confirmed } = reduceHold(get().hold, event);
    set({ hold: state });
    if (confirmed) useInfrastructureStore.getState().requestDisconnect();
  },
}));
