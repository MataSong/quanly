import client from "./client";

export const backtestApi = {
  run: (payload: any) => client.post("/backtests/run", payload),
  list: () => client.get("/backtests"),
  detail: (id: number) => client.get(`/backtests/${id}`),
};
