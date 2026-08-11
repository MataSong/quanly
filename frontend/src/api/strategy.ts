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
};
