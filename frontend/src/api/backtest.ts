import http from "./http";

// ── Interfaces ────────────────────────────────────────────────────────────────

export interface BacktestMetrics {
  total_return: number | null;
  annualized_return: number | null;
  max_drawdown: number | null;
  sharpe: number | null;
  win_rate: number | null;
  profit_factor: number | null; // null means ∞
  trade_count: number | null;
}

export interface EquityPoint {
  ts: number;   // milliseconds
  equity: number;
}

export interface BacktestTrade {
  id: number;
  side: "buy" | "sell";
  ts: number;   // milliseconds
  price: number;
  sz: number;
  fee: number;
  pnl: number;
}

export interface BacktestItem {
  id: number;
  strategy: number;
  strategy_name?: string;
  symbol: string;
  bar: string;
  status: "pending" | "running" | "done" | "error";
  metrics: BacktestMetrics | null;
  error_msg: string | null;
  created_at: string;
}

export interface BacktestDetail extends BacktestItem {
  equity_curve: EquityPoint[];
  trades: BacktestTrade[];
}

export interface CreateBacktestPayload {
  strategy_id: number;
  symbol: string;
  bar: string;
  start_ts: number;   // milliseconds
  end_ts: number;     // milliseconds
  params?: Record<string, unknown>;
  init_cash?: number;
  fee_rate?: number;
}

// ── API functions ─────────────────────────────────────────────────────────────

/** POST /backtest/backtests — create a new backtest (returns pending item) */
export async function createBacktest(payload: CreateBacktestPayload): Promise<BacktestItem> {
  const r = await http.post<BacktestItem>("/backtest/backtests", payload);
  return r.data;
}

/** GET /backtest/backtests — list my backtests (no equity_curve/trades) */
export async function listBacktests(): Promise<BacktestItem[]> {
  const r = await http.get<BacktestItem[]>("/backtest/backtests");
  return r.data;
}

/** GET /backtest/backtests/{id} — full detail including equity_curve and trades */
export async function getBacktest(id: number): Promise<BacktestDetail> {
  const r = await http.get<BacktestDetail>(`/backtest/backtests/${id}`);
  return r.data;
}
