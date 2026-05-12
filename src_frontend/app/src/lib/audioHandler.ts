import { send } from "@/lib/websocket";

const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const PLAYBACK_SPEED_FACTOR = 1.11; // 11% speedup for snappier Nova Sonic voice
const PLAYBACK_SAMPLE_RATE = Math.round(OUTPUT_SAMPLE_RATE * PLAYBACK_SPEED_FACTOR);
const CHUNK_DURATION_MS = 100;
const SAMPLES_PER_CHUNK = (INPUT_SAMPLE_RATE * CHUNK_DURATION_MS) / 1000;

let audioContext: AudioContext | null = null;
let mediaStream: MediaStream | null = null;
let workletNode: ScriptProcessorNode | null = null;
let isCapturing = false;

let playbackContext: AudioContext | null = null;
let nextPlayTime = 0;

export function isAudioActive(): boolean {
  return isCapturing;
}

export async function startAudioCapture(): Promise<void> {
  if (isCapturing) return;

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      sampleRate: INPUT_SAMPLE_RATE,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  audioContext = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
  const source = audioContext.createMediaStreamSource(mediaStream);

  const bufferSize = 4096;
  workletNode = audioContext.createScriptProcessor(bufferSize, 1, 1);

  let sampleBuffer: Float32Array = new Float32Array(0);

  workletNode.onaudioprocess = (event: AudioProcessingEvent) => {
    if (!isCapturing) return;
    const inputData = event.inputBuffer.getChannelData(0);

    const combined = new Float32Array(sampleBuffer.length + inputData.length);
    combined.set(sampleBuffer);
    combined.set(inputData, sampleBuffer.length);
    sampleBuffer = combined;

    while (sampleBuffer.length >= SAMPLES_PER_CHUNK) {
      const chunk = sampleBuffer.slice(0, SAMPLES_PER_CHUNK);
      sampleBuffer = sampleBuffer.slice(SAMPLES_PER_CHUNK);
      sendAudioChunk(chunk);
    }
  };

  source.connect(workletNode);
  workletNode.connect(audioContext.destination);
  isCapturing = true;

  if (!playbackContext) {
    playbackContext = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE });
  }
  nextPlayTime = 0;
}

export function stopAudioCapture(): void {
  isCapturing = false;

  if (workletNode) {
    workletNode.disconnect();
    workletNode = null;
  }

  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }

  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }

  nextPlayTime = 0;
}

function sendAudioChunk(samples: Float32Array): void {
  const pcm16 = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }

  const base64 = arrayBufferToBase64(pcm16.buffer);
  send({ type: "audio_input", payload: { audio: base64 } });
}

export function playAudioOutput(base64Pcm24k: string): void {
  if (!playbackContext) {
    playbackContext = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE });
  }

  if (playbackContext.state === "suspended") {
    playbackContext.resume();
  }

  const pcmBytes = base64ToArrayBuffer(base64Pcm24k);
  const pcm16 = new Int16Array(pcmBytes);
  const float32 = new Float32Array(pcm16.length);
  for (let i = 0; i < pcm16.length; i++) {
    float32[i] = pcm16[i] / 32768.0;
  }

  const buffer = playbackContext.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE);
  buffer.getChannelData(0).set(float32);

  const source = playbackContext.createBufferSource();
  source.buffer = buffer;
  source.connect(playbackContext.destination);

  const now = playbackContext.currentTime;
  if (nextPlayTime <= now) {
    nextPlayTime = now + 0.01;
  }
  source.start(nextPlayTime);
  nextPlayTime += buffer.duration;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
