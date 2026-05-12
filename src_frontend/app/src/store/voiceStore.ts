import { create } from "zustand";
import { subscribe } from "@/lib/websocket";
import { playAudioOutput } from "@/lib/audioHandler";
import type { WsMessage } from "@/lib/websocket";

interface Transcript {
  id: string;
  speaker: "agent" | "human";
  text: string;
  timestamp: string;
}

interface VoiceStore {
  callActive: boolean;
  transcripts: Transcript[];
  setCallActive: (active: boolean) => void;
  addTranscript: (speaker: "agent" | "human", text: string) => void;
  clearTranscripts: () => void;
}

export const useVoiceStore = create<VoiceStore>((set) => ({
  callActive: false,
  transcripts: [],

  setCallActive: (active: boolean) => set({ callActive: active }),

  addTranscript: (speaker: "agent" | "human", text: string) =>
    set((state) => ({
      transcripts: [
        ...state.transcripts.slice(-49),
        {
          id: crypto.randomUUID(),
          speaker,
          text,
          timestamp: new Date().toISOString(),
        },
      ],
    })),

  clearTranscripts: () => set({ transcripts: [] }),
}));

function handleVoiceMessages(message: WsMessage): void {
  const { type, payload } = message;

  if (type === "audio_output") {
    const audio = payload.audio as string;
    if (audio) {
      playAudioOutput(audio);
    }
  }

  if (type === "call_transcript") {
    const speaker = (payload.speaker as "agent" | "human") || "agent";
    const text = payload.text as string;
    if (text) {
      useVoiceStore.getState().addTranscript(speaker, text);
    }
  }

  if (type === "call_started") {
    useVoiceStore.getState().setCallActive(true);
  }

  if (type === "incident_resolved" || type === "system_status") {
    if (type === "system_status" && (payload.phase as string) === "HEALTHY") {
      useVoiceStore.getState().setCallActive(false);
    }
  }
}

subscribe(handleVoiceMessages);
