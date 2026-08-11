import client from "./client";

export const assetsApi = {
  summary: (env: string) => client.get("/assets/summary", { params: { env } }),
  bills: (env: string) => client.get("/assets/bills", { params: { env } }),
  sync: (env: string) => client.post("/assets/sync", { env }),
};
