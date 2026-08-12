import client from "./client";

export const strategyApi = {
  list: () => client.get("/strategies/"),
  get: (id: number) => client.get(`/strategies/${id}/`),
  create: (name: string, source: string) =>
    client.post("/strategies/", { name, source }),
  update: (id: number, name: string, source: string) =>
    client.put(`/strategies/${id}/`, { name, source }),
  remove: (id: number) => client.delete(`/strategies/${id}/`),
  run: (id: number, payload: any) => client.post(`/strategies/${id}/run`, payload),
  stop: (runId: number) => client.post(`/strategy-runs/${runId}/stop`),
  runs: (strategyId?: number) =>
    client.get("/strategy-runs", { params: { strategy: strategyId } }),
  logs: (runId: number) => client.get(`/strategy-runs/${runId}/logs`),
  credentials: (env: string) =>
    client.get("/trading/credentials", { params: { env } }),
  batchRun: (payload: {
    template_id: number;
    symbols: string[];
    env: string;
    credential_id?: number;
    interval_sec?: number;
  }) => client.post("/strategy/tasks/batch-run", payload),
  tasksOverview: () => client.get("/strategy/tasks"),
  batchStop: (batchId: string) =>
    client.post("/strategy/tasks/batch-stop", { batch_id: batchId }),
  visualSchemas: () => client.get("/strategy/visual/schemas"),
  visualPreview: (kind: string, config: any) =>
    client.post("/strategy/visual/preview", { kind, config }),
  codeValidate: (source: string) => client.post("/strategy/code/validate", { source }),
  codeDryrun: (source: string, symbol = "BTC-USDT") =>
    client.post("/strategy/code/dryrun", { source, symbol }),
  createFull: (payload: any) => client.post("/strategies/", payload),
  updateFull: (id: number, payload: any) => client.put(`/strategies/${id}/`, payload),
};
