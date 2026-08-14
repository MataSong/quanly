import http from "./http";

// ── Request payloads ──────────────────────────────────────────────────────────

export interface PlaceOrderPayload {
  credential_id: number;
  inst_type: "SPOT" | "SWAP";
  inst_id: string;
  side: "buy" | "sell";
  ord_type: "market" | "limit";
  sz: string;
  /** Required when ord_type === "limit" */
  px?: string;
  /** Required for SWAP */
  pos_side?: "long" | "short";
  /** "cash" for SPOT; "cross" | "isolated" for SWAP */
  td_mode?: "cash" | "cross" | "isolated";
  reduce_only?: boolean;
}

export interface CancelOrderPayload {
  credential_id: number;
  inst_id: string;
  ord_id: string;
}

// ── Response shapes ───────────────────────────────────────────────────────────

export interface OkxOrderResult {
  ordId: string;
  clOrdId: string;
}

export interface PlaceOrderResponse {
  order: Record<string, unknown>;
  okx: OkxOrderResult;
}

export interface OrderItem {
  ordId: string;
  clOrdId: string;
  instId: string;
  instType: string;
  side: string;
  ordType: string;
  sz: string;
  px: string;
  state: string;
  fillSz: string;
  avgPx: string;
  cTime: string;
  uTime: string;
  [key: string]: unknown;
}

export interface PositionItem {
  instId: string;
  instType: string;
  posSide: string;
  pos: string;
  avgPx: string;
  upl: string;
  uplRatio: string;
  lever: string;
  mgnMode: string;
  cTime: string;
  uTime: string;
  [key: string]: unknown;
}

export interface BalanceItem {
  ccy: string;
  bal: string;
  availBal: string;
  frozenBal: string;
  [key: string]: unknown;
}

export interface OrdersResponse {
  data: OrderItem[];
}

export interface PositionsResponse {
  data: PositionItem[];
}

export interface BalanceResponse {
  data: BalanceItem[];
}

// ── API functions ─────────────────────────────────────────────────────────────

/** POST /trading/order — place an order */
export async function placeOrder(payload: PlaceOrderPayload): Promise<PlaceOrderResponse> {
  const r = await http.post<PlaceOrderResponse>("/trading/order", payload);
  return r.data;
}

/** POST /trading/cancel — cancel an open order */
export async function cancelOrder(payload: CancelOrderPayload): Promise<void> {
  await http.post("/trading/cancel", payload);
}

/** GET /trading/orders — list pending orders */
export async function getOrders(credentialId: number, instType?: string): Promise<OrderItem[]> {
  const params: Record<string, string | number> = { credential_id: credentialId };
  if (instType) params.inst_type = instType;
  const r = await http.get<OrdersResponse>("/trading/orders", { params });
  return r.data.data ?? [];
}

/** GET /trading/positions — list open positions */
export async function getPositions(
  credentialId: number,
  instType?: string,
): Promise<PositionItem[]> {
  const params: Record<string, string | number> = { credential_id: credentialId };
  if (instType) params.inst_type = instType;
  const r = await http.get<PositionsResponse>("/trading/positions", { params });
  return r.data.data ?? [];
}

/** GET /trading/balance — account balance */
export async function getBalance(credentialId: number): Promise<BalanceItem[]> {
  const r = await http.get<BalanceResponse>("/trading/balance", {
    params: { credential_id: credentialId },
  });
  return r.data.data ?? [];
}
