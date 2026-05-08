export type SceneState =
  | "HEALTHY"
  | "INCIDENT_DETECTED"
  | "DIAGNOSING"
  | "CALLING"
  | "RECOVERING"
  | "RESOLVED";

export interface BuildingConfig {
  id: string;
  label: string;
  xPct: number;
  yPct: number;
  width: number;
  height: number;
  color: string;
}

export interface ConnectionConfig {
  from: string;
  to: string;
}

export interface CharacterConfig {
  id: string;
  color: string;
  speed: number;
}
