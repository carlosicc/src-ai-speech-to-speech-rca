export interface WsMessage {
  type: string;
  payload: Record<string, unknown>;
  timestamp?: string;
}

type MessageHandler = (message: WsMessage) => void;

function getWsUrl(): string {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}
const WS_URL = getWsUrl();
const RECONNECT_DELAY = 2000;
const MAX_RECONNECT_DELAY = 30000;

let socket: WebSocket | null = null;
let reconnectAttempts = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let intentionallyClosed = false;

const handlers: Set<MessageHandler> = new Set();

function connect(): void {
  if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) {
    return;
  }

  intentionallyClosed = false;
  socket = new WebSocket(WS_URL);

  socket.onopen = () => {
    reconnectAttempts = 0;
  };

  socket.onmessage = (event) => {
    try {
      const message: WsMessage = JSON.parse(event.data);
      for (const handler of handlers) {
        handler(message);
      }
    } catch {
      // ignore malformed messages
    }
  };

  socket.onclose = () => {
    socket = null;
    if (!intentionallyClosed) {
      scheduleReconnect();
    }
  };

  socket.onerror = () => {
    socket?.close();
  };
}

function scheduleReconnect(): void {
  const delay = Math.min(RECONNECT_DELAY * 2 ** reconnectAttempts, MAX_RECONNECT_DELAY);
  reconnectAttempts++;
  reconnectTimer = setTimeout(connect, delay);
}

export function subscribe(handler: MessageHandler): () => void {
  handlers.add(handler);
  if (!socket || socket.readyState === WebSocket.CLOSED) {
    connect();
  }
  return () => {
    handlers.delete(handler);
  };
}

export function send(message: WsMessage): void {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message));
  }
}

export function disconnect(): void {
  intentionallyClosed = true;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  socket?.close();
  socket = null;
}

export function isConnected(): boolean {
  return socket?.readyState === WebSocket.OPEN;
}
