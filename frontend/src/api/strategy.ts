import http from "./http";

// ── Interfaces ────────────────────────────────────────────────────────────────

export interface Strategy {
  id: number;
  name: string;
  code_ref: string;
  default_params: Record<string, unknown>;
  is_builtin: boolean;
  // 商城字段
  owner_username?: string;
  is_owner?: boolean;
  template_ref?: string;
  params?: Record<string, unknown>;
  visibility?: "private" | "public";
  status?: "draft" | "pending" | "approved" | "rejected";
  description?: string;
  reject_reason?: string;
  updated_at?: string;
  source_type?: "builtin" | "uploaded" | "code";
  code?: string;
  check_status?: "pending" | "passed" | "failed";
  check_report?: Record<string, unknown>;
  performance?: StrategyPerformance;
}

export interface StrategyPerformance {
  run_count: number;
  user_count: number;
  order_count: number;
  reference_backtest: Record<string, unknown> | null;
}

export interface CreateStrategyPayload {
  name: string;
  source_type?: "uploaded" | "code";
  template_ref?: string;
  params?: Record<string, unknown>;
  code?: string;
  description?: string;
  visibility?: "private" | "public";
}

export interface StrategyRun {
  id: number;
  name: string;
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
  name?: string;
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

// ── 策略商城 API ────────────────────────────────────────────────────────────────

export interface MarketplaceParams {
  search?: string;
  filter?: "all" | "builtin" | "user";
  page?: number;
  page_size?: number;
}

export interface Paginated<T> {
  results: T[];
  total: number;
  page: number;
  page_size: number;
}

/** GET /strategy/marketplace — 商城分页+搜索+筛选(公开审核过+内置) */
export async function getMarketplace(
  params: MarketplaceParams = {},
): Promise<Paginated<Strategy>> {
  const r = await http.get<Paginated<Strategy>>("/strategy/marketplace", { params });
  return r.data;
}

/** GET /strategy/mine — 我创建的策略 */
export async function getMyStrategies(): Promise<Strategy[]> {
  const r = await http.get<Strategy[]>("/strategy/mine");
  return r.data;
}

/** GET /strategy/strategies/{id} — 策略详情(含 performance) */
export async function getStrategyDetail(id: number): Promise<Strategy> {
  const r = await http.get<Strategy>(`/strategy/strategies/${id}`);
  return r.data;
}

/** POST /strategy/strategies/create — 创建参数化实例 */
export async function createStrategy(payload: CreateStrategyPayload): Promise<Strategy> {
  const r = await http.post<Strategy>("/strategy/strategies/create", payload);
  return r.data;
}

/** PUT /strategy/strategies/{id} — 编辑自己的策略(改动重置为 draft) */
export async function updateStrategy(
  id: number,
  payload: Partial<CreateStrategyPayload>,
): Promise<Strategy> {
  const r = await http.put<Strategy>(`/strategy/strategies/${id}`, payload);
  return r.data;
}

/** DELETE /strategy/strategies/{id} — 删除自己的策略(有运行引用会 400) */
export async function deleteStrategy(id: number): Promise<void> {
  await http.delete(`/strategy/strategies/${id}`);
}

/** POST /strategy/strategies/{id}/submit — 提交审核(private→public+pending) */
export async function submitStrategy(id: number): Promise<Strategy> {
  const r = await http.post<Strategy>(`/strategy/strategies/${id}/submit`);
  return r.data;
}

/** POST /strategy/strategies/{id}/check — 重跑代码检测(语法+AST+试运行) */
export async function checkStrategy(id: number): Promise<Strategy> {
  const r = await http.post<Strategy>(`/strategy/strategies/${id}/check`);
  return r.data;
}

/** GET /strategy/admin/pending — 待审核策略列表(需 strategy:audit) */
export async function getAdminPending(): Promise<Strategy[]> {
  const r = await http.get<Strategy[]>("/strategy/admin/pending");
  return r.data;
}

/** POST /strategy/admin/strategies/{id}/review — 审核通过/驳回(需 strategy:audit) */
export async function reviewStrategy(
  id: number,
  action: "approve" | "reject",
  reason?: string,
): Promise<Strategy> {
  const r = await http.post<Strategy>(`/strategy/admin/strategies/${id}/review`, {
    action,
    reason,
  });
  return r.data;
}
