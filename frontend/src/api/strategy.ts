import http from "./http";

// ── Interfaces ────────────────────────────────────────────────────────────────

export interface Strategy {
  id: number;
  name: string;
  code_ref: string;
  default_params: Record<string, unknown>;
  is_builtin: boolean;
}

export interface StrategyRun {
  id: number;
  strategy: number;
  strategy_name: string;
  credential: number;
  credential_label: string;
  credential_env: "sim" | "live";
  symbol: string;
  params: Record<string, unknown>;
  status: "pending" | "running" | "stopped" | "error";
  created_at: string;
  updated_at: string;
}

export interface StrategyLog {
  level: string;
  message: string;
  ts: string;
}

export interface CreateRunPayload {
  strategy_id: number;
  credential_id: number;
  symbol: string;
  params: Record<string, unknown>;
}

// ── API functions ─────────────────────────────────────────────────────────────

/** GET /strategy/strategies — list built-in strategies */
export async function listStrategies(): Promise<Strategy[]> {
  const r = await http.get<Strategy[]>("/strategy/strategies");
  return r.data;
}

/** GET /strategy/runs — list my strategy runs */
export async function listRuns(): Promise<StrategyRun[]> {
  const r = await http.get<StrategyRun[]>("/strategy/runs");
  return r.data;
}

/** POST /strategy/runs — create a new strategy run */
export async function createRun(payload: CreateRunPayload): Promise<StrategyRun> {
  const r = await http.post<StrategyRun>("/strategy/runs", payload);
  return r.data;
}

/** GET /strategy/runs/{id} — get run detail */
export async function getRun(id: number): Promise<StrategyRun> {
  const r = await http.get<StrategyRun>(`/strategy/runs/${id}`);
  return r.data;
}

/** POST /strategy/runs/{id}/start — start a run (spins up container) */
export async function startRun(id: number): Promise<{ detail: string; run_id: number }> {
  const r = await http.post<{ detail: string; run_id: number }>(`/strategy/runs/${id}/start`);
  return r.data;
}

/** POST /strategy/runs/{id}/stop — stop a running run */
export async function stopRun(id: number): Promise<{ detail: string }> {
  const r = await http.post<{ detail: string }>(`/strategy/runs/${id}/stop`);
  return r.data;
}

/** GET /strategy/runs/{id}/logs — fetch historical logs */
export async function getRunLogs(id: number): Promise<StrategyLog[]> {
  const r = await http.get<StrategyLog[]>(`/strategy/runs/${id}/logs`);
  return r.data;
}
