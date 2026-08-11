import client from "./client";

export const financeApi = {
  products: (env: string, category?: string) =>
    client.get("/finance/products", { params: { env, category } }),
  holdings: (env: string) => client.get("/finance/holdings", { params: { env } }),
  subscribe: (env: string, productId: number, amount: string) =>
    client.post("/finance/subscribe", { env, product_id: productId, amount }),
  redeem: (env: string, holdingId: number) =>
    client.post(`/finance/redeem/${holdingId}`, { env }),
  transfer: (payload: any) => client.post("/finance/transfer", payload),
  transfers: (env: string) => client.get("/finance/transfers", { params: { env } }),
};
