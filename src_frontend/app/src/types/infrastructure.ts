export type LinkStatus = "connected" | "disconnecting" | "disconnected" | "restoring";

export interface InfrastructureLink {
  id: string;
  source: string;
  target: string;
  protocol: string;
  port: number;
  status: LinkStatus;
}

export interface LinkUpdatePayload {
  link_id: string;
  status: LinkStatus | "error";
  request_id?: string;
  message?: string;
}
