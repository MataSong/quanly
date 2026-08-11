import client from "./client";

export interface OrderPayload {
  env: string;
  inst_type: "SPOT" | "MARGIN" | "SWAP" | "FUTURES" | "OPTION" | "ETF";
  symbol: string;
  side: "buy" | "sell";
  ord_type: "market" | "limit";
  sz: string;
  px?: string;
  td_mode?: string;
  lever?: number;
  credential_id?: number;
  strike?: string;
  expiry?: string;
  opt_type?: string;
  tp_px?: string;
  sl_px?: string;
}

export const tradingApi = {
  placeOrder: (p: OrderPayload) => client.post("/trading/orders/place", p),
  listCredentials: (env: string) =>
    client.get("/trading/credentials", { params: { env } }),
  listOrders: (env: string, state?: string) =>
    client.get("/trading/orders", { params: { env, state } }),
  cancelOrder: (id: number) => client.post(`/trading/orders/${id}/cancel`),
  listPositions: (env: string) =>
    client.get("/trading/positions", { params: { env } }),
  closePosition: (id: number) => client.post(`/trading/positions/${id}/close`),
  listBalances: (env: string) =>
    client.get("/trading/balances", { params: { env } }),
  listTrades: (env: string) =>
    client.get("/trading/trades", { params: { env } }),
};
