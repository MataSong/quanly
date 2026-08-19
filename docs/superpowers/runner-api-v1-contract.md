# Runner API v1 契约（冻结）

**状态**: 冻结（frozen）。**只增不改**——不得修改/删除现有端点路径、请求字段、响应字段的语义。任何破坏性变更必须新开 `/runner/v2/*`，v1 永久保留。

## 为什么冻结

策略运行在独立 Docker 容器里（`quanly-strategy-runner` 镜像，celery 用 docker SDK 裸起，不属 docker-compose）。容器里的 `runner.py` 打的是这些 HTTP 端点。**运行中的旧容器跑的是打进旧镜像的 runner.py**——后端热更新/重构后，只要 v1 端点契约不变，旧容器就能继续正常通信。这是"系统重构升级不影响用户正在运行的策略"的技术保证。

**破坏 v1 契约 = 打断所有运行中的用户策略容器。** 改契约前必须走 v2 并保留 v1。

## 鉴权

所有 v1 端点用 `X-Run-Token` header（RunTokenAuthentication）。token 明文只在容器 env（RUN_TOKEN），后端只存 sha256 hash，`resolve_run` 要求 `status=running` 且 hash 匹配。401 → 容器立即退出。

## 端点

基址：`{BACKEND_URL}/api/strategy/runner/v1`（BACKEND_URL 默认 `http://backend:8000`）。
旧无版本路径 `/api/strategy/runner/*` 保留为 v1 别名（兼容更早镜像）。

### GET /runner/v1/candles
拉历史 K 线（走公共行情，无需 credential）。
- Query: `bar`（如 "1m"，默认 "1m"）、`limit`（默认 100，clamp 1-300）。
- 响应 200: `{"candles": [{"ts": int, "o": str, "h": str, "l": str, "c": str, "vol": str, "volCcy": str}, ...]}`（oldest-first）。
- 错误: 401（token 失效）/ 502（OKX 错误）。

### POST /runner/v1/order
下单（用 run 关联的 credential，密钥永不出后端）。
- Body: `{"side": "buy"|"sell", "sz": str, "ord_type": "market"|"limit"(默认 market), "px": str|null}`。
- 响应 200: `{"ordId": str}`。
- 错误: 400（参数）/ 401 / 502（OKX 错误）。

### POST /runner/v1/log
写策略日志（落库 + WS 广播）。
- Body: `{"level": "info"|"buy"|"sell"|"warn"|"error", "message": str}`。
- 响应 201: `{"id": int}`。best-effort，runner 侧不因 log 失败而崩。

## 策略接口契约（on_tick）

用户/内置策略实现 `on_tick(ctx, params)`：
- `ctx.candles(bar="1m", limit=100) -> list[dict]`（同 /candles 响应的 candles）。
- `ctx.buy(sz, ord_type="market", px=None) -> str`（ordId）。
- `ctx.sell(sz, ord_type="market", px=None) -> str`。
- `ctx.log(level, message) -> None`。
- `ctx.price() -> float | None`（最新收盘价）。
- `params`：策略参数 dict（内置从 default_params，用户实例从 params）。

on_tick 契约同样冻结（改 ctx 方法签名 = 打断旧容器）。扩展只能加新方法/新可选参数，不改现有。

## 变更记录

- v1（2026-08-19）冻结：candles / order / log 三端点 + on_tick 契约。
