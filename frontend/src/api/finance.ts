import client from "./client";

export const financeApi = {
  transfer: (payload: any) => client.post("/finance/transfer", payload),
  transfers: (env: string) => client.get("/finance/transfers", { params: { env } }),
};
