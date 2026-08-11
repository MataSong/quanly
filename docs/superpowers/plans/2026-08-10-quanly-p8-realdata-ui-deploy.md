# P8 全面去 Mock 化、UI 统一与部署一键化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 彻底移除项目中所有 mock 数据与 mock 代码路径，全链路改用真实 OKX 数据；统一 UI 玻璃风格；把部署做成小白可用的一键化流程。

**Architecture:** OKX 成为唯一数据真相源，本地库仅作缓存与展示。新增 OKX 私有 WebSocket 采集器订阅账户/持仓/订单推送，替代原本地 MockEngine 的撮合与风控推算。前端替换所有原生表单控件为自研 Glass 组件族，行情选择器改为可搜索下拉框。部署改用 Caddy 自动证书 + 一键 init/update 脚本。

**Tech Stack:** Django 5 + DRF + Channels + Celery + Redis + PostgreSQL + InfluxDB；python-okx SDK；Vue 3 + TypeScript + Vite + vue-i18n；Docker Compose + Caddy。

**关键约束（实现前必读）：**
- 后端测试用 pytest + `@pytest.mark.django_db` + `monkeypatch`（见 `apps/trading/test_okx_engine.py`）。测试库为 sqlite，不需真实 DB/OKX 连接，OKX SDK 一律 monkeypatch。
- 前端**无测试框架**（package.json 无 vitest）。前端任务的"验证"用 `npm run build`（`vue-tsc -b && vite build`）做类型检查 + 构建通过，并辅以手动浏览器验证。
- 项目**无 git**。每个"Commit"步骤改为**手动快照**：`cp` 关键文件或在完成一个块后用 `tar` 打包备份到 `C:\App\Project\`。不要求 git commit。
- 交易对当前硬编码在 `backend/apps/market/constants.py` 的 `SYMBOLS`（仅 3 个）。collector 只订阅这 3 个。去硬编码需同时处理后端 constants 与前端各处。

---

## 文件结构总览

**块 A（后端去 mock + 同步）新建/修改：**
- 删除 `backend/apps/market/mockfeed.py`
- 删除 `backend/apps/market/test_mockfeed.py`
- 修改 `backend/config/settings.py`（删开关）
- 修改 `backend/apps/trading/engine.py`（删 MockEngine，重写 OKXEngine）
- 修改 `backend/apps/trading/prices.py`（删 mockfeed 兜底）
- 修改 `backend/apps/market/management/commands/run_collector.py`（删 _run_mock）
- 修改 `backend/apps/market/views.py`（删 MARKET_FEED 分支）
- 修改 `backend/apps/strategy/runner_api.py`（删 MARKET_FEED 分支）
- 修改 `backend/apps/trading/reconcile.py`（改为对比 OKX REST 余额）
- 新建 `backend/apps/trading/sync.py`（OKX 余额/持仓/订单/账单同步逻辑）
- 新建 `backend/apps/trading/management/commands/run_private_ws.py`（OKX 私有 WS 采集器）
- 新建 `backend/apps/assets/sync_views.py`（手动/进入页触发全量同步的 REST 端点）

**块 B/C/E（前端）新建/修改：**
- 新建 `frontend/src/components/GlassSelect.vue`
- 新建 `frontend/src/components/GlassNumber.vue`
- 新建 `frontend/src/components/GlassSlider.vue`
- 新建 `frontend/src/components/GlassCheckbox.vue`
- 新建 `frontend/src/components/SymbolSelect.vue`
- 新建 `frontend/src/components/Spinner.vue`
- 新建 `frontend/src/composables/useToast.ts`
- 修改各 view（Market/Trade/Transfer/Finance/StrategyDetail/Backtest/Keys/Pagination）

**块 D（前后端遗留补全）：**
- 修改 `backend/apps/backtest/engine.py`（真实历史 K 线）
- 删除 `backend/apps/finance/views.py` 的 `c2c`；修改 `products/subscribe/redeem`
- 修改前端 `Transfer.vue`、`api/finance.ts`、i18n（删 C2C）

**块 F（部署）新建：**
- 新建 `deploy/init.sh`、`deploy/update.sh`、`deploy/backup.sh`、`deploy/restore.sh`
- 新建 `Caddyfile`；修改 `docker-compose.prod.yml`

---

## 块 A：去 Mock 化 + OKX 数据同步（后端核心）

> 依赖注意：A7（删 mockfeed.py）必须在 D1（回测改真实 K 线）完成后执行，因为 `backtest/engine.py` 仍 import mockfeed。执行时先做 A1-A6、A8-A10，回到 D1 后再做 A7。

### Task A1：删除 mockfeed 的测试文件，解除快照

**Files:**
- Delete: `backend/apps/market/test_mockfeed.py`

- [ ] **Step 1：快照备份关键文件**

```bash
cd /c/App/Project/quanly/backend
cp apps/trading/prices.py apps/trading/prices.py.bak
cp apps/trading/engine.py apps/trading/engine.py.bak
cp config/settings.py config/settings.py.bak
cp apps/market/management/commands/run_collector.py apps/market/management/commands/run_collector.py.bak
```

- [ ] **Step 2：删除 mockfeed 测试**

```bash
rm apps/market/test_mockfeed.py
```

- [ ] **Step 3：确认删除**

Run: `ls apps/market/test_mockfeed.py`
Expected: `No such file or directory`

### Task A2：重写 prices.py — 去 mockfeed 兜底

**Files:**
- Modify: `backend/apps/trading/prices.py`

- [ ] **Step 1：写失败测试**

Test: `backend/apps/trading/test_prices.py`

```python
import pytest
from apps.trading import prices


def test_get_last_price_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(prices, "_redis_get", lambda symbol: None)
    assert prices.get_last_price("BTC-USDT") is None


def test_get_last_price_reads_redis(monkeypatch):
    monkeypatch.setattr(prices, "_redis_get", lambda symbol: 65000.0)
    assert prices.get_last_price("BTC-USDT") == 65000.0
```

- [ ] **Step 2：运行测试确认失败**

Run: `.venv/bin/python -m pytest apps/trading/test_prices.py -v`
Expected: FAIL（`_redis_get` 不存在 / 仍返回 mock 值）

- [ ] **Step 3：重写 prices.py**

```python
"""最新价读取：仅走 Redis 缓存（由 collector 写入），无假数据兜底。"""
import json

import redis
from django.conf import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL)
    return _client


def _key(symbol: str) -> str:
    return f"last_price:{symbol}"


def set_last_price(symbol: str, price: float) -> None:
    _get_client().set(_key(symbol), json.dumps(price), ex=300)


def _redis_get(symbol: str):
    raw = _get_client().get(_key(symbol))
    if raw is None:
        return None
    return json.loads(raw)


def get_last_price(symbol: str):
    """返回最新价 float，读不到返回 None（调用方需自行处理）。"""
    return _redis_get(symbol)
```

- [ ] **Step 4：运行测试确认通过**

Run: `.venv/bin/python -m pytest apps/trading/test_prices.py -v`
Expected: PASS

- [ ] **Step 5：快照**

```bash
cp apps/trading/prices.py apps/trading/prices.py.done
```

### Task A3：删除 settings 开关，新增 OKX 私有 WS 配置

**Files:**
- Modify: `backend/config/settings.py`

- [ ] **Step 1：删除 MARKET_FEED / EXCHANGE_MODE 两个开关**

在 `settings.py` 中删除：

```python
MARKET_FEED = os.environ.get("MARKET_FEED", "okx")
EXCHANGE_MODE = os.environ.get("EXCHANGE_MODE", "mock")
```

- [ ] **Step 2：新增 OKX 私有 WS + 同步配置**

在 REDIS_URL 附近新增：

```python
OKX_PRIVATE_WS_LIVE = os.environ.get(
    "OKX_PRIVATE_WS_LIVE", "wss://ws.okx.com:8443/ws/v5/private"
)
OKX_PRIVATE_WS_SIM = os.environ.get(
    "OKX_PRIVATE_WS_SIM", "wss://wspap.okx.com:8443/ws/v5/private"
)
OKX_PUBLIC_WS_LIVE = os.environ.get(
    "OKX_PUBLIC_WS_LIVE", "wss://ws.okx.com:8443/ws/v5/public"
)
OKX_PUBLIC_WS_SIM = os.environ.get(
    "OKX_PUBLIC_WS_SIM", "wss://wspap.okx.com:8443/ws/v5/public"
)
OKX_SYNC_INTERVAL = int(os.environ.get("OKX_SYNC_INTERVAL", "20"))
```

- [ ] **Step 3：全局 grep 确认无残留引用**

Run: `grep -rn "MARKET_FEED\|EXCHANGE_MODE" apps/ config/`
Expected: 仅剩 A5/A6 待改的文件（run_collector.py、market/views.py、strategy/runner_api.py、finance/views.py）

### Task A4：重写 engine.py — 独立 OKXEngine，删除 MockEngine

**Files:**
- Modify: `backend/apps/trading/engine.py`

- [ ] **Step 1：写失败测试**

Test: `backend/apps/trading/test_okx_engine.py`（在现有文件追加）

```python
def test_get_engine_returns_okx_engine():
    from apps.trading.engine import OKXEngine, get_engine

    assert isinstance(get_engine(), OKXEngine)


def test_no_mock_engine_symbol():
    import apps.trading.engine as engine_mod

    assert not hasattr(engine_mod, "MockEngine")
    assert not hasattr(engine_mod, "MOCK_INITIAL_USDT")
```

- [ ] **Step 2：运行测试确认失败**

Run: `.venv/bin/python -m pytest apps/trading/test_okx_engine.py -v`
Expected: FAIL（MockEngine 仍存在）

- [ ] **Step 3：重写 engine.py**

```python
"""OKX 真实交易引擎：下单/撤单/平仓直调 OKXAdapter。

不再本地撮合/结算：成交、持仓、余额变化由 OKX 私有 WS（run_private_ws）
与 REST 同步（sync.py）回填。本模块只负责把用户动作转发给交易所并回填订单号。
"""
from decimal import Decimal

from .models import OrderState

D = Decimal


def _get_balance(user, env, ccy):
    """获取余额行，不存在则建零余额（不再注资 mock 初始资金）。"""
    from .models import Balance

    bal, _ = Balance.objects.get_or_create(
        user=user, env=env, ccy=ccy, defaults={"total": D("0")}
    )
    return bal


class OKXEngine:
    """真实 OKX 交易引擎。下单/撤单/平仓走 OKXAdapter，状态回填由 WS/REST 同步负责。"""

    def _adapter(self, order):
        from apps.credentials.models import Env
        from apps.exchanges.factory import AdapterFactory

        env = Env.SIM if order.env == "sim" else Env.LIVE
        return AdapterFactory.create("okx", env, order.credential)

    def place(self, order):
        from apps.exchanges.types import InstType as XInstType
        from apps.exchanges.types import OrderRequest

        adapter = self._adapter(order)
        req = OrderRequest(
            symbol=order.symbol,
            inst_type=XInstType(order.inst_type),
            side=order.side,
            ord_type=order.ord_type,
            sz=float(order.sz),
            px=float(order.px) if order.px else None,
            td_mode=order.td_mode,
        )
        result = adapter.place_order(req)
        order.exchange_order_id = result.order_id
        order.state = OrderState.LIVE if result.state == "live" else order.state
        order.save()
        return order

    def cancel(self, order):
        adapter = self._adapter(order)
        adapter.cancel_order(order.exchange_order_id, symbol=order.symbol)
        order.state = OrderState.CANCELED
        order.save()
        return order

    def close_position(self, position):
        from apps.credentials.models import Env
        from apps.exchanges.factory import AdapterFactory

        env = Env.SIM if position.env == "sim" else Env.LIVE
        cred = (
            position.user.exchangecredential_set.filter(
                env=position.env, exchange="okx"
            ).first()
            if hasattr(position.user, "exchangecredential_set")
            else None
        )
        adapter = AdapterFactory.create("okx", env, cred)
        adapter.close_position(position.symbol, position.pos_side, "cross")
        return position


def get_engine():
    return OKXEngine()
```

- [ ] **Step 4：运行测试确认通过**

Run: `.venv/bin/python -m pytest apps/trading/test_okx_engine.py -v`
Expected: PASS

- [ ] **Step 5：确认无残留 MockEngine / check_risk / match_pending 引用**

Run: `grep -rn "MockEngine\|match_pending\|check_risk\|MOCK_INITIAL" apps/`
Expected: 仅 A5 待改的 run_collector.py（其 `_match_and_notify` 调 check_risk/match_pending，A5 一并删除）

### Task A5：重写 run_collector.py — 仅 OKX，写 last_price

**Files:**
- Modify: `backend/apps/market/management/commands/run_collector.py`

- [ ] **Step 1：删除 `_run_mock` 与 `_match_and_notify`**

删除 `handle()` 中对 `settings.MARKET_FEED` 的分支判断，直接调用 `_run_okx()`；删除 `_run_mock` 方法和调用 engine.match_pending/check_risk 的 `_match_and_notify` 方法。

- [ ] **Step 2：在 `_publish_candle` 中写入 last_price**

在 collector 收到公共行情推送、发布 K 线的位置，新增写缓存：

```python
from apps.trading.prices import set_last_price

# 在 _publish_candle（或收到 ticker/candle 的回调）内，拿到 close 价后：
set_last_price(symbol, float(close_px))
```

- [ ] **Step 3：公共 WS 域名按 env 取配置**

```python
from django.conf import settings

url = settings.OKX_PUBLIC_WS_SIM if self.env == "sim" else settings.OKX_PUBLIC_WS_LIVE
```

- [ ] **Step 4：Django check 通过**

Run: `.venv/bin/python manage.py check`
Expected: `System check identified no issues`

- [ ] **Step 5：快照**

```bash
cp apps/market/management/commands/run_collector.py apps/market/management/commands/run_collector.py.done
```

### Task A6：删除 views/runner_api 的 MARKET_FEED 分支

**Files:**
- Modify: `backend/apps/market/views.py`
- Modify: `backend/apps/strategy/runner_api.py`

- [ ] **Step 1：market/views.py 去分支**

删除所有 `if settings.MARKET_FEED == ...` 判断，固定走 OKX/真实数据分支。

- [ ] **Step 2：strategy/runner_api.py 去分支**

同上，删除 MARKET_FEED 判断，固定真实数据路径。

- [ ] **Step 3：grep 确认**

Run: `grep -rn "MARKET_FEED" apps/`
Expected: 无输出

- [ ] **Step 4：Django check**

Run: `.venv/bin/python manage.py check`
Expected: no issues

### Task A7：删除 mockfeed.py（依赖 D1 完成后执行）

**Files:**
- Delete: `backend/apps/market/mockfeed.py`

- [ ] **Step 1：确认无 import 残留**

Run: `grep -rn "mockfeed" apps/`
Expected: 无输出（若有，说明 D1 未完成或 A2 未清干净，先补齐再删）

- [ ] **Step 2：删除文件**

```bash
rm apps/market/mockfeed.py
```

- [ ] **Step 3：Django check + 全量测试**

Run: `.venv/bin/python manage.py check && .venv/bin/python -m pytest apps/ -q`
Expected: no issues；测试通过

### Task A8：新增 sync.py（OKX 数据 upsert）+ run_private_ws 命令

**Files:**
- Create: `backend/apps/trading/sync.py`
- Create: `backend/apps/trading/management/commands/run_private_ws.py`

- [ ] **Step 1：写失败测试**

Test: `backend/apps/trading/test_sync.py`

```python
import pytest
from decimal import Decimal

from apps.trading import sync
from apps.trading.models import Balance


@pytest.mark.django_db
def test_upsert_balances_writes_rows(django_user_model):
    user = django_user_model.objects.create(username="u1")
    rows = [
        type("B", (), {"ccy": "USDT", "total": 1000.0, "available": 900.0, "frozen": 100.0})(),
        type("B", (), {"ccy": "BTC", "total": 0.5, "available": 0.5, "frozen": 0.0})(),
    ]
    sync.upsert_balances(user, "sim", rows)
    usdt = Balance.objects.get(user=user, env="sim", ccy="USDT")
    assert usdt.total == Decimal("1000.0")
    assert usdt.frozen == Decimal("100.0")
    assert Balance.objects.filter(user=user, env="sim").count() == 2
```

- [ ] **Step 2：运行测试确认失败**

Run: `.venv/bin/python -m pytest apps/trading/test_sync.py -v`
Expected: FAIL（sync 模块不存在）

- [ ] **Step 3：写 sync.py**

```python
"""OKX 真实数据 upsert：把 REST/WS 拉到的余额/持仓/订单写入本地表并推前端。"""
import json
from decimal import Decimal

import redis
from django.conf import settings

from .models import Balance, Order, OrderState, Position, PosSide

D = Decimal


def _redis():
    return redis.from_url(settings.REDIS_URL)


def _publish(user_id, env, payload):
    _redis().publish(f"trade:{user_id}:{env}", json.dumps(payload))


def upsert_balances(user, env, rows):
    """rows: 可迭代对象，元素含 ccy/total/available/frozen 属性。"""
    for r in rows:
        Balance.objects.update_or_create(
            user=user,
            env=env,
            ccy=r.ccy,
            defaults={
                "total": D(str(r.total)),
                "frozen": D(str(getattr(r, "frozen", 0) or 0)),
            },
        )
    _publish(user.id, env, {"type": "balance_update"})


def upsert_positions(user, env, rows):
    """rows: 元素含 symbol/side/qty/avg_price/upl/liq_price。qty=0 视为平仓。"""
    seen = set()
    for r in rows:
        pos_side = PosSide.LONG if str(r.side).lower() == "long" else PosSide.SHORT
        seen.add((r.symbol, pos_side))
        Position.objects.update_or_create(
            user=user,
            env=env,
            symbol=r.symbol,
            pos_side=pos_side,
            defaults={
                "qty": D(str(r.qty)),
                "avg_px": D(str(r.avg_price)),
                "liq_px": D(str(getattr(r, "liq_price", 0) or 0)),
            },
        )
    Position.objects.filter(user=user, env=env).exclude(
        symbol__in=[s for s, _ in seen]
    ).update(qty=D("0"))
    _publish(user.id, env, {"type": "position_update"})


def upsert_order(user, env, o):
    """o: 元素含 order_id/symbol/state/filled_sz/avg_px。"""
    state_map = {
        "live": OrderState.LIVE,
        "filled": OrderState.FILLED,
        "canceled": OrderState.CANCELED,
        "partially_filled": OrderState.LIVE,
    }
    Order.objects.filter(user=user, env=env, exchange_order_id=o.order_id).update(
        state=state_map.get(str(o.state).lower(), OrderState.LIVE),
        filled_sz=D(str(getattr(o, "filled_sz", 0) or 0)),
        avg_px=D(str(getattr(o, "avg_px", 0) or 0)),
    )
    _publish(user.id, env, {"type": "order_update"})


def full_sync(user, env, adapter):
    """进入页面/启动时的 REST 全量校正。"""
    upsert_balances(user, env, adapter.get_balances())
    upsert_positions(user, env, adapter.get_positions())
```

- [ ] **Step 4：运行测试确认通过**

Run: `.venv/bin/python -m pytest apps/trading/test_sync.py -v`
Expected: PASS

- [ ] **Step 5：写 run_private_ws 管理命令**

```python
"""OKX 私有 WebSocket 常驻采集器：订阅 account/positions/orders，回填本地表。"""
import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "运行 OKX 私有 WS 采集器（按用户凭证登录，实时回填余额/持仓/订单）"

    def add_arguments(self, parser):
        parser.add_argument("--env", choices=["sim", "live"], default="sim")

    def handle(self, *args, **opts):
        env = opts["env"]
        asyncio.run(self._run(env))

    async def _run(self, env):
        from apps.credentials.models import ExchangeCredential
        from apps.exchanges.okx.adapter import OKXAdapter

        creds = [
            c for c in ExchangeCredential.objects.filter(env=env, exchange="okx")
        ]
        if not creds:
            self.stderr.write("无可用凭证，退出")
            return
        await asyncio.gather(*[self._run_one(c, env) for c in creds])

    async def _run_one(self, cred, env):
        from okx.websocket.WsPrivateAsync import WsPrivateAsync

        from apps.exchanges.okx.adapter import OKXAdapter
        from apps.trading import sync

        adapter = OKXAdapter(env=("sim" if env == "sim" else "live"), credential=cred)
        api_key, secret, passphrase = adapter._decrypt_keys()
        url = (
            settings.OKX_PRIVATE_WS_SIM if env == "sim" else settings.OKX_PRIVATE_WS_LIVE
        )
        user = cred.user

        def _on_account(msg):
            sync.upsert_balances(user, env, adapter.parse_ws_balances(msg))

        def _on_positions(msg):
            sync.upsert_positions(user, env, adapter.parse_ws_positions(msg))

        def _on_orders(msg):
            for o in adapter.parse_ws_orders(msg):
                sync.upsert_order(user, env, o)

        backoff = 1
        while True:
            try:
                ws = WsPrivateAsync(
                    apiKey=api_key,
                    passphrase=passphrase,
                    secretKey=secret,
                    url=url,
                    useServerTime=False,
                )
                await ws.start()
                await ws.subscribe([{"channel": "account"}], _on_account)
                await ws.subscribe([{"channel": "positions", "instType": "ANY"}], _on_positions)
                await ws.subscribe([{"channel": "orders", "instType": "ANY"}], _on_orders)
                backoff = 1
                while True:
                    await asyncio.sleep(30)
            except Exception as e:  # noqa: BLE001
                self.stderr.write(f"WS 断线重连({backoff}s): {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
```

- [ ] **Step 6：为 adapter 补 WS 解析方法与 `_decrypt_keys`**

在 `apps/exchanges/okx/adapter.py` 中确认/补充：`_decrypt_keys()` 返回 `(api_key, secret, passphrase)`；`parse_ws_balances/parse_ws_positions/parse_ws_orders(msg)` 把 OKX 推送 `msg["data"]` 转成含所需属性的对象列表（复用 REST 解析同款字段：`eq/frozenBal`、`instId/posSide/pos/avgPx/liqPx`、`ordId/state/accFillSz/avgPx`）。

- [ ] **Step 7：Django check**

Run: `.venv/bin/python manage.py check`
Expected: no issues

### Task A9：同步 REST 端点 + Celery 定时校正 + service.summarize 防护

**Files:**
- Create: `backend/apps/assets/sync_views.py`
- Modify: `backend/apps/assets/service.py`（_price None 防护）
- Modify: `backend/apps/trading/tasks.py`（新增 celery 定时同步）

- [ ] **Step 1：service.summarize 的 _price 加 None 防护**

```python
def _price(symbol: str) -> Decimal:
    p = get_last_price(symbol)
    return D(str(p)) if p is not None else D("0")
```

- [ ] **Step 2：写 sync_views.py（进入页面触发全量同步）**

```python
"""手动/进入页触发 OKX 全量同步。"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.credentials.models import Env, ExchangeCredential
from apps.exchanges.factory import AdapterFactory
from apps.trading import sync


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def full_sync(request):
    env = request.data.get("env", "sim")
    cred = ExchangeCredential.objects.filter(
        user=request.user, env=env, exchange="okx"
    ).first()
    if not cred:
        return Response({"detail": "未配置 OKX 凭证"}, status=400)
    x_env = Env.SIM if env == "sim" else Env.LIVE
    adapter = AdapterFactory.create("okx", x_env, cred)
    try:
        sync.full_sync(request.user, env, adapter)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"同步失败: {e}"}, status=502)
    return Response({"ok": True})
```

- [ ] **Step 3：挂路由**

在 `apps/assets/urls.py` 增加：`path("sync/", sync_views.full_sync)`。

- [ ] **Step 4：Celery 定时校正任务**

在 `apps/trading/tasks.py` 新增：

```python
@shared_task
def periodic_okx_sync():
    from apps.credentials.models import Env, ExchangeCredential
    from apps.exchanges.factory import AdapterFactory
    from apps.trading import sync

    for cred in ExchangeCredential.objects.filter(exchange="okx"):
        x_env = Env.SIM if cred.env == "sim" else Env.LIVE
        try:
            adapter = AdapterFactory.create("okx", x_env, cred)
            sync.full_sync(cred.user, cred.env, adapter)
        except Exception:  # noqa: BLE001
            continue
```

在 celery beat 配置里以 `OKX_SYNC_INTERVAL` 秒注册该任务。

- [ ] **Step 5：Django check**

Run: `.venv/bin/python manage.py check`
Expected: no issues

### Task A10：重写 reconcile.py — 对比 OKX REST 实拉余额

**Files:**
- Modify: `backend/apps/trading/reconcile.py`

- [ ] **Step 1：去 MOCK_INITIAL_USDT 依赖，改真实对账**

```python
"""对账：本地 Balance 与 OKX REST 实拉余额比对，输出差异。"""
from decimal import Decimal

from apps.credentials.models import Env, ExchangeCredential
from apps.exchanges.factory import AdapterFactory
from apps.trading.models import Balance

D = Decimal


def reconcile(user, env: str) -> list[dict]:
    cred = ExchangeCredential.objects.filter(
        user=user, env=env, exchange="okx"
    ).first()
    if not cred:
        return []
    x_env = Env.SIM if env == "sim" else Env.LIVE
    adapter = AdapterFactory.create("okx", x_env, cred)
    remote = {b.ccy: D(str(b.total)) for b in adapter.get_balances()}
    diffs = []
    for bal in Balance.objects.filter(user=user, env=env):
        r = remote.get(bal.ccy, D("0"))
        if abs(r - bal.total) > D("0.00000001"):
            diffs.append(
                {"ccy": bal.ccy, "local": float(bal.total), "remote": float(r)}
            )
    return diffs
```

- [ ] **Step 2：grep 确认 MOCK 依赖清除**

Run: `grep -rn "MOCK_INITIAL" apps/`
Expected: 无输出

- [ ] **Step 3：Django check + 全量测试**

Run: `.venv/bin/python manage.py check && .venv/bin/python -m pytest apps/ -q`
Expected: no issues；通过

---

## 块 C：自研 Glass 表单组件族（前端）

> 先做 C 再做 B：SymbolSelect 复用 GlassSelect 的下拉/玻璃样式约定。前端无测试框架，验证统一用 `cd frontend && npm run build`（vue-tsc 类型检查 + vite 构建）。所有组件用 `defineModel`（Vue 3.4+）或 `modelValue`+`update:modelValue` 实现 v-model，样式全部用 glass.css 的 CSS 变量（`--glass-bg`、`--glass-bg-strong`、`--glass-border`、`--fg`、`--accent`），自动适配深浅主题。

### Task C1：GlassSelect 组件

**Files:**
- Create: `frontend/src/components/GlassSelect.vue`

- [ ] **Step 1：编写组件**

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'

interface Option { label: string; value: string | number }
const props = defineProps<{
  modelValue: string | number
  options: Option[]
  placeholder?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [string | number] }>()

const open = ref(false)
const current = computed(
  () => props.options.find((o) => o.value === props.modelValue)?.label ?? props.placeholder ?? '请选择'
)
function pick(o: Option) {
  emit('update:modelValue', o.value)
  open.value = false
}
</script>

<template>
  <div class="glass-select" :class="{ open }">
    <button type="button" class="gs-trigger" @click="open = !open">
      <span>{{ current }}</span>
      <span class="gs-arrow">▾</span>
    </button>
    <transition name="gs-fade">
      <ul v-if="open" class="gs-menu">
        <li
          v-for="o in options"
          :key="o.value"
          class="gs-item"
          :class="{ active: o.value === modelValue }"
          @click="pick(o)"
        >
          {{ o.label }}
        </li>
      </ul>
    </transition>
    <div v-if="open" class="gs-backdrop" @click="open = false" />
  </div>
</template>

<style scoped>
.glass-select { position: relative; display: inline-block; min-width: 140px; }
.gs-trigger {
  width: 100%; display: flex; justify-content: space-between; align-items: center;
  gap: 8px; padding: 8px 12px; border-radius: 10px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--fg); cursor: pointer; backdrop-filter: blur(12px);
}
.gs-arrow { transition: transform .2s; opacity: .7; }
.glass-select.open .gs-arrow { transform: rotate(180deg); }
.gs-menu {
  position: absolute; z-index: 30; top: calc(100% + 6px); left: 0; right: 0;
  margin: 0; padding: 6px; list-style: none; max-height: 260px; overflow-y: auto;
  background: var(--glass-bg-strong); border: 1px solid var(--glass-border);
  border-radius: 12px; backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0,0,0,.25);
}
.gs-item { padding: 8px 10px; border-radius: 8px; color: var(--fg); cursor: pointer; }
.gs-item:hover { background: rgba(255,255,255,.08); }
.gs-item.active { background: var(--accent); color: #fff; }
.gs-backdrop { position: fixed; inset: 0; z-index: 20; }
.gs-fade-enter-active, .gs-fade-leave-active { transition: opacity .15s, transform .15s; }
.gs-fade-enter-from, .gs-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
```

- [ ] **Step 2：类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 构建成功，无 vue-tsc 报错

### Task C2：GlassNumber 组件（带样式化加减按钮）

**Files:**
- Create: `frontend/src/components/GlassNumber.vue`

- [ ] **Step 1：编写组件**

```vue
<script setup lang="ts">
const props = defineProps<{
  modelValue: number | string
  step?: number
  min?: number
  max?: number
  placeholder?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [number] }>()

function clamp(v: number): number {
  if (props.min != null && v < props.min) v = props.min
  if (props.max != null && v > props.max) v = props.max
  return v
}
function bump(dir: number) {
  const step = props.step ?? 1
  const cur = Number(props.modelValue) || 0
  emit('update:modelValue', clamp(cur + dir * step))
}
function onInput(e: Event) {
  const v = Number((e.target as HTMLInputElement).value)
  emit('update:modelValue', Number.isNaN(v) ? 0 : v)
}
</script>

<template>
  <div class="glass-number">
    <button type="button" class="gn-btn" @click="bump(-1)">−</button>
    <input
      class="gn-input" type="text" inputmode="decimal"
      :value="modelValue" :placeholder="placeholder" @input="onInput"
    />
    <button type="button" class="gn-btn" @click="bump(1)">+</button>
  </div>
</template>

<style scoped>
.glass-number {
  display: inline-flex; align-items: stretch; border-radius: 10px; overflow: hidden;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  backdrop-filter: blur(12px);
}
.gn-btn {
  width: 34px; border: none; background: transparent; color: var(--fg);
  font-size: 18px; cursor: pointer; transition: background .15s;
}
.gn-btn:hover { background: rgba(255,255,255,.1); }
.gn-input {
  flex: 1; min-width: 0; border: none; background: transparent; color: var(--fg);
  text-align: center; padding: 8px 4px; outline: none;
}
</style>
```

- [ ] **Step 2：类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 成功

### Task C3：GlassSlider 组件（杠杆滑块）

**Files:**
- Create: `frontend/src/components/GlassSlider.vue`

- [ ] **Step 1：编写组件**

```vue
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ modelValue: number; min?: number; max?: number; step?: number }>()
const emit = defineEmits<{ 'update:modelValue': [number] }>()
const min = computed(() => props.min ?? 1)
const max = computed(() => props.max ?? 125)
const pct = computed(() => ((props.modelValue - min.value) / (max.value - min.value)) * 100)
function onInput(e: Event) {
  emit('update:modelValue', Number((e.target as HTMLInputElement).value))
}
</script>

<template>
  <div class="glass-slider">
    <input
      type="range" class="gs-range" :min="min" :max="max" :step="step ?? 1"
      :value="modelValue" :style="{ '--pct': pct + '%' }" @input="onInput"
    />
    <span class="gs-value">{{ modelValue }}x</span>
  </div>
</template>

<style scoped>
.glass-slider { display: flex; align-items: center; gap: 12px; }
.gs-range {
  flex: 1; -webkit-appearance: none; appearance: none; height: 6px; border-radius: 6px;
  background: linear-gradient(to right, var(--accent) var(--pct), var(--glass-border) var(--pct));
  outline: none;
}
.gs-range::-webkit-slider-thumb {
  -webkit-appearance: none; width: 18px; height: 18px; border-radius: 50%;
  background: var(--accent); cursor: pointer; border: 2px solid #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,.3);
}
.gs-range::-moz-range-thumb {
  width: 18px; height: 18px; border-radius: 50%; background: var(--accent);
  cursor: pointer; border: 2px solid #fff;
}
.gs-value { min-width: 44px; text-align: right; color: var(--fg); font-variant-numeric: tabular-nums; }
</style>
```

- [ ] **Step 2：类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 成功

### Task C4：GlassCheckbox 组件

**Files:**
- Create: `frontend/src/components/GlassCheckbox.vue`

- [ ] **Step 1：编写组件**

```vue
<script setup lang="ts">
const props = defineProps<{ modelValue: boolean; label?: string }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()
</script>

<template>
  <label class="glass-checkbox" @click="emit('update:modelValue', !modelValue)">
    <span class="gc-box" :class="{ checked: modelValue }">
      <span v-if="modelValue" class="gc-tick">✓</span>
    </span>
    <span v-if="label" class="gc-label">{{ label }}</span>
  </label>
</template>

<style scoped>
.glass-checkbox { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
.gc-box {
  width: 20px; height: 20px; border-radius: 6px; display: flex; align-items: center;
  justify-content: center; background: var(--glass-bg); border: 1px solid var(--glass-border);
  transition: background .15s, border-color .15s;
}
.gc-box.checked { background: var(--accent); border-color: var(--accent); }
.gc-tick { color: #fff; font-size: 13px; line-height: 1; }
.gc-label { color: var(--fg); }
</style>
```

- [ ] **Step 2：类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 成功

### Task C5：替换所有原生控件

**Files:**
- Modify: `frontend/src/views/Trade.vue`（select 266/277；number 299/340/344/353/355；range 348）
- Modify: `frontend/src/views/Transfer.vue`（select 57/61/67；number 73）
- Modify: `frontend/src/views/Finance.vue`（number 96）
- Modify: `frontend/src/views/StrategyDetail.vue`（select 114/121/129；number 137；checkbox 158）
- Modify: `frontend/src/views/Backtest.vue`（select 193/199；number 205/209/213；checkbox 258）
- Modify: `frontend/src/views/Keys.vue`（select 53）
- Modify: `frontend/src/components/Pagination.vue`（select 59）

- [ ] **Step 1：逐文件替换**

对每个 `<select>` 换成 `<GlassSelect v-model="x" :options="[...]" />`；每个 `<input type="number">` 换成 `<GlassNumber v-model="x" :step="..." :min="..." />`；杠杆 `<input type="range">` 换 `<GlassSlider v-model="lever" :min="1" :max="125" />`；`<input type="checkbox">` 换 `<GlassCheckbox v-model="x" label="..." />`。各文件顶部 `import` 对应组件。原生 `<select>` 的 `<option>` 列表转为 `options` 数组（`{label,value}`）。

- [ ] **Step 2：grep 确认无裸露原生控件**

Run: `cd frontend && grep -rn "type=\"number\"\|type=\"range\"\|type=\"checkbox\"\|<select" src/views src/components/Pagination.vue`
Expected: 无输出（除 Glass 组件内部实现）

- [ ] **Step 3：类型检查 + 构建 + 浏览器验证**

Run: `cd frontend && npm run build`
Expected: 成功。随后 `npm run dev`，在深浅主题下逐页目视确认控件玻璃风统一、加减/滑块可用。

---

## 块 B：行情交易对搜索下拉选择器（前端）

> 依赖 C1（GlassSelect 的样式约定）。SymbolSelect 是带搜索输入的下拉，选项来自 `/market/symbols`。

### Task B1：SymbolSelect 组件

**Files:**
- Create: `frontend/src/components/SymbolSelect.vue`

- [ ] **Step 1：编写组件**

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()

const open = ref(false)
const keyword = ref('')
const symbols = ref<string[]>([])
const loading = ref(false)

const filtered = computed(() =>
  keyword.value
    ? symbols.value.filter((s) => s.toLowerCase().includes(keyword.value.toLowerCase()))
    : symbols.value
)

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/market/symbols')
    symbols.value = (data.symbols ?? data ?? []).map((x: any) => (typeof x === 'string' ? x : x.symbol))
  } finally {
    loading.value = false
  }
}
function pick(s: string) {
  emit('update:modelValue', s)
  open.value = false
  keyword.value = ''
}
onMounted(load)
</script>

<template>
  <div class="symbol-select" :class="{ open }">
    <button type="button" class="ss-trigger" @click="open = !open">
      <span>{{ modelValue || '选择交易对' }}</span>
      <span class="ss-arrow">▾</span>
    </button>
    <transition name="ss-fade">
      <div v-if="open" class="ss-panel">
        <input
          v-model="keyword" class="ss-search" placeholder="搜索交易对…" autofocus
        />
        <ul class="ss-list">
          <li v-if="loading" class="ss-empty">加载中…</li>
          <li v-else-if="!filtered.length" class="ss-empty">无匹配</li>
          <li
            v-for="s in filtered" :key="s" class="ss-item"
            :class="{ active: s === modelValue }" @click="pick(s)"
          >
            {{ s }}
          </li>
        </ul>
      </div>
    </transition>
    <div v-if="open" class="ss-backdrop" @click="open = false" />
  </div>
</template>

<style scoped>
.symbol-select { position: relative; display: inline-block; min-width: 180px; }
.ss-trigger {
  width: 100%; display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-radius: 10px; background: var(--glass-bg);
  border: 1px solid var(--glass-border); color: var(--fg); cursor: pointer;
  backdrop-filter: blur(12px);
}
.ss-arrow { opacity: .7; transition: transform .2s; }
.symbol-select.open .ss-arrow { transform: rotate(180deg); }
.ss-panel {
  position: absolute; z-index: 30; top: calc(100% + 6px); left: 0; right: 0;
  background: var(--glass-bg-strong); border: 1px solid var(--glass-border);
  border-radius: 12px; padding: 8px; backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0,0,0,.25);
}
.ss-search {
  width: 100%; box-sizing: border-box; padding: 8px 10px; margin-bottom: 6px;
  border-radius: 8px; background: var(--glass-bg); border: 1px solid var(--glass-border);
  color: var(--fg); outline: none;
}
.ss-list { list-style: none; margin: 0; padding: 0; max-height: 240px; overflow-y: auto; }
.ss-item { padding: 8px 10px; border-radius: 8px; color: var(--fg); cursor: pointer; }
.ss-item:hover { background: rgba(255,255,255,.08); }
.ss-item.active { background: var(--accent); color: #fff; }
.ss-empty { padding: 10px; text-align: center; opacity: .6; color: var(--fg); }
.ss-backdrop { position: fixed; inset: 0; z-index: 20; }
.ss-fade-enter-active, .ss-fade-leave-active { transition: opacity .15s, transform .15s; }
.ss-fade-enter-from, .ss-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
```

- [ ] **Step 2：类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 成功

### Task B2：Market.vue 用 SymbolSelect 替换平铺按钮

**Files:**
- Modify: `frontend/src/views/Market.vue`（`.tabs` + `v-for` 按钮，约 51-59 行）

- [ ] **Step 1：替换**

删除 `.tabs` 那排 `v-for` 按钮，改为：

```vue
<SymbolSelect v-model="symbol" @update:modelValue="onSymbolChange" />
```

顶部 `import SymbolSelect from '@/components/SymbolSelect.vue'`。`onSymbolChange` 里触发原 `selectSymbol` 的重新订阅逻辑。删除本地不再使用的 `loadSymbols` 平铺渲染代码（仍可保留请求，但改由 SymbolSelect 自身加载）。

- [ ] **Step 2：Trade / StrategyDetail / Backtest 复用**

这三处的交易对选择也换成 `<SymbolSelect v-model="symbol" />`，删除各自的硬编码 `SYMBOLS`（Trade.vue:12 等，与 D4 联动）。

- [ ] **Step 3：类型检查 + 构建 + 浏览器验证**

Run: `cd frontend && npm run build`
Expected: 成功。`npm run dev` 确认行情页为可搜索下拉，输入关键词实时筛选。

---

## 块 D：遗留补全（前后端）

### Task D1：回测接真实历史 K 线（解除 A7 阻塞）

**Files:**
- Modify: `backend/apps/backtest/engine.py`（第 63 行 `mockfeed.history_candles`）

- [ ] **Step 1：写失败测试**

Test: `backend/apps/backtest/test_engine.py`

```python
import pytest
from apps.backtest import engine


@pytest.mark.django_db
def test_history_candles_uses_okx_not_mockfeed(monkeypatch):
    called = {}

    def fake_fetch(symbol, bar, limit):
        called["ok"] = True
        return [[0, "1", "2", "0.5", "1.5", "10"]]

    monkeypatch.setattr(engine, "_fetch_candles", fake_fetch)
    rows = engine._fetch_candles("BTC-USDT", "1m", 100)
    assert called.get("ok")
    assert rows
```

- [ ] **Step 2：运行确认失败**

Run: `.venv/bin/python -m pytest apps/backtest/test_engine.py -v`
Expected: FAIL（`_fetch_candles` 不存在）

- [ ] **Step 3：改 engine.py — 优先 InfluxDB，不足 OKX REST 补齐**

将原 `from apps.market import mockfeed` / `mockfeed.history_candles(...)` 替换为：

```python
def _fetch_candles(symbol, bar, limit):
    """优先读 InfluxDB 已采集 K 线，不足则用 OKX REST 补齐。返回 OKX 格式列表。"""
    from apps.market.influx import read_candles  # 现有 Influx 读取封装
    from apps.exchanges.factory import AdapterFactory
    from apps.credentials.models import Env

    rows = read_candles(symbol, bar, limit)
    if len(rows) >= limit:
        return rows[-limit:]
    adapter = AdapterFactory.create("okx", Env.LIVE, None)
    return adapter.get_candles(symbol, bar=bar, limit=limit)
```

回测主循环改为调用 `_fetch_candles(symbol, bar, limit)`。若 `apps.market.influx` 无 `read_candles`，用现有 Influx 查询封装名替换（执行时 grep `influx` 确认实际函数名）。

- [ ] **Step 4：运行确认通过**

Run: `.venv/bin/python -m pytest apps/backtest/test_engine.py -v`
Expected: PASS

- [ ] **Step 5：确认 backtest 不再 import mockfeed**

Run: `grep -rn "mockfeed" apps/backtest/`
Expected: 无输出（此后可执行 A7 删 mockfeed.py）

### Task D2：删除 C2C 功能（后端）

**Files:**
- Modify: `backend/apps/finance/views.py`（删 `c2c()` 约 164-179 行）
- Modify: `backend/apps/finance/urls.py`（删 c2c 路由）

- [ ] **Step 1：删除 c2c 视图与路由**

删除 `finance/views.py` 的 `c2c()` 函数；删除 `finance/urls.py` 中对应 `path("c2c/...")`。

- [ ] **Step 2：grep 确认无残留**

Run: `grep -rn "c2c\|C2C" apps/`
Expected: 无输出

- [ ] **Step 3：Django check**

Run: `.venv/bin/python manage.py check`
Expected: no issues

### Task D3：理财全接真实 OKX（后端）

**Files:**
- Modify: `backend/apps/finance/views.py`（删 `SEED`/`_seed`，`products`/`subscribe`/`redeem` 走真实）

- [ ] **Step 1：products 列表走真实 OKX 理财接口**

删除本地 `SEED` 常量与 `_seed()`；`products` 视图改为调 `OKXAdapter.get_savings_products()`（若 adapter 无此方法，按 python-okx `FundingAPI.get_saving_balance` / `Finance` 相应接口补一个 adapter 方法）。删除 `_okx()` 里读 `EXCHANGE_MODE` 的分支，固定真实。

- [ ] **Step 2：subscribe / redeem 走真实**

`subscribe` → `adapter.subscribe_savings(ccy, amount)`；`redeem` → `adapter.redeem_savings(ccy, amount)`（adapter 已有 `subscribe_savings/redeem_savings`）。移除本地记账（本地 FinanceHolding 仅作展示缓存，由同步回填）。

- [ ] **Step 3：Django check**

Run: `.venv/bin/python manage.py check`
Expected: no issues

### Task D4：去硬编码交易对（前后端）

**Files:**
- Modify: `backend/apps/market/constants.py`（`SYMBOLS` 仅保留为 collector 默认订阅回退，标注）
- Modify: 前端各处硬编码 `SYMBOLS`（Trade.vue:12 等）

- [ ] **Step 1：后端 `/market/symbols` 返回真实 OKX instruments**

确认 `market/views.py` 的 symbols 端点从 OKX `get_instruments` 动态取（不再返回 constants.SYMBOLS）。`constants.SYMBOLS` 仅保留作为 collector 无网络时的最小回退，注释说明。

- [ ] **Step 2：前端删除硬编码 SYMBOLS**

前端所有 `const SYMBOLS = [...]` 删除，改由 SymbolSelect / `/market/symbols` 动态加载（与 B2 联动）。

- [ ] **Step 3：grep 确认**

Run: `cd frontend && grep -rn "SYMBOLS" src/`
Expected: 无硬编码数组残留

### Task D5：删除 C2C（前端）

**Files:**
- Modify: `frontend/src/views/Transfer.vue`（删 C2C 区块）
- Modify: `frontend/src/api/finance.ts`（删 c2c 调用）
- Modify: `frontend/src/router/index.ts`（删 C2C 路由，若有）
- Modify: `frontend/src/i18n/*`（删 C2C 文案）

- [ ] **Step 1：删除前端 C2C 入口/页面/路由/i18n**

删除 Transfer.vue 中 C2C 相关 UI 与逻辑；`api/finance.ts` 删 c2c 请求函数；router 删 C2C route；i18n 各语言文件删 C2C 键。

- [ ] **Step 2：grep 确认**

Run: `cd frontend && grep -rin "c2c" src/`
Expected: 无输出

- [ ] **Step 3：类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 成功

---

## 块 E：加载态与错误提示（前端）

### Task E1：Spinner 组件

**Files:**
- Create: `frontend/src/components/Spinner.vue`

- [ ] **Step 1：编写组件**

```vue
<script setup lang="ts">
defineProps<{ size?: number; label?: string }>()
</script>

<template>
  <div class="spinner-wrap">
    <span class="spinner" :style="{ width: (size ?? 24) + 'px', height: (size ?? 24) + 'px' }" />
    <span v-if="label" class="spinner-label">{{ label }}</span>
  </div>
</template>

<style scoped>
.spinner-wrap { display: inline-flex; align-items: center; gap: 8px; }
.spinner {
  display: inline-block; border-radius: 50%;
  border: 2px solid var(--glass-border); border-top-color: var(--accent);
  animation: spin .7s linear infinite;
}
.spinner-label { color: var(--fg); opacity: .8; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
```

- [ ] **Step 2：构建**

Run: `cd frontend && npm run build`
Expected: 成功

### Task E2：useToast composable

**Files:**
- Create: `frontend/src/composables/useToast.ts`

- [ ] **Step 1：编写 composable（全局单例 toast 队列）**

```typescript
import { ref } from 'vue'

export interface Toast { id: number; text: string; type: 'info' | 'error' | 'success' }

const toasts = ref<Toast[]>([])
let seq = 0

export function useToast() {
  function push(text: string, type: Toast['type'] = 'info', ms = 3000) {
    const id = ++seq
    toasts.value.push({ id, text, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, ms)
  }
  return {
    toasts,
    info: (t: string) => push(t, 'info'),
    error: (t: string) => push(t, 'error', 5000),
    success: (t: string) => push(t, 'success'),
  }
}
```

- [ ] **Step 2：在 App.vue 渲染 toast 容器**

在 `App.vue` 引入 `useToast`，渲染 `toasts` 列表为玻璃风右上角浮层（复用 glass.css 变量，`.type==='error'` 用红色边）。

- [ ] **Step 3：构建**

Run: `cd frontend && npm run build`
Expected: 成功

### Task E3：client.ts 拦截器兜底 + 各页面 loading

**Files:**
- Modify: `frontend/src/api/client.ts`（响应拦截器）
- Modify: 各 view（请求期间显示 Spinner）

- [ ] **Step 1：client.ts 响应拦截器统一报错**

在 axios 实例响应拦截器的 reject 分支：透传 OKX 报错信息到 toast：

```typescript
import { useToast } from '@/composables/useToast'

client.interceptors.response.use(
  (r) => r,
  (err) => {
    const { error } = useToast()
    const msg = err?.response?.data?.detail || err?.response?.data?.msg || err.message || '请求失败'
    error(String(msg))
    return Promise.reject(err)
  }
)
```

- [ ] **Step 2：各页面请求期间显示 Spinner**

在资产总览、行情、交易、理财等页面，API 请求包一层 `loading` ref，模板中 `<Spinner v-if="loading" label="加载中…" />`。

- [ ] **Step 3：构建 + 浏览器验证**

Run: `cd frontend && npm run build`
Expected: 成功。`npm run dev` 确认请求期间有加载反馈；断开 OKX 或填错凭证时有清晰错误提示。

---

## 块 F：部署一键化（运维脚本）

> 目标：全新服务器一条命令初始化；代码迭代一条命令热更新；证书自动化；自动备份/恢复。执行时先确认现有 `docker-compose.prod.yml` 的服务名（web/daphne/celery/beat/collector/redis/postgres/influxdb 等），脚本按实际服务名调整。

### Task F1：Caddyfile（自动证书）

**Files:**
- Create: `Caddyfile`

- [ ] **Step 1：编写 Caddyfile**

```
{$DOMAIN} {
    encode gzip
    handle /api/* {
        reverse_proxy web:8000
    }
    handle /ws/* {
        reverse_proxy daphne:8001
    }
    handle {
        root * /srv/frontend
        try_files {path} /index.html
        file_server
    }
    tls {$ACME_EMAIL}
}
```

Caddy 自动为 `$DOMAIN` 申请/续期 Let's Encrypt 证书（`$DOMAIN`/`$ACME_EMAIL` 由 `.env.prod` 注入）。

### Task F2：init.sh（一键初始化）

**Files:**
- Create: `deploy/init.sh`

- [ ] **Step 1：编写脚本**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env.prod"
if [ -f "$ENV_FILE" ]; then
  echo "$ENV_FILE 已存在，跳过生成（如需重置请先备份删除）。"
else
  echo "== 首次初始化：生成配置 =="
  read -rp "域名(如 trade.example.com): " DOMAIN
  read -rp "证书邮箱: " ACME_EMAIL
  read -rsp "数据库密码(留空自动生成): " DB_PASSWORD; echo
  [ -z "$DB_PASSWORD" ] && DB_PASSWORD="$(openssl rand -hex 16)"
  DJANGO_SECRET_KEY="$(openssl rand -base64 48 | tr -d '\n')"
  SECRET_ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
  cat > "$ENV_FILE" <<EOF
DOMAIN=$DOMAIN
ACME_EMAIL=$ACME_EMAIL
POSTGRES_PASSWORD=$DB_PASSWORD
DATABASE_URL=postgres://quanly:$DB_PASSWORD@postgres:5432/quanly
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
SECRET_ENCRYPTION_KEY=$SECRET_ENCRYPTION_KEY
REDIS_URL=redis://redis:6379/0
DEBUG=0
ALLOWED_HOSTS=$DOMAIN
EOF
  chmod 600 "$ENV_FILE"
  echo "已生成 $ENV_FILE"
fi

echo "== 拉起全部服务 =="
docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" up -d --build
echo "== 等待数据库就绪并迁移 =="
docker compose -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml exec -T web python manage.py collectstatic --noinput || true
echo "== 完成。访问 https://$(grep ^DOMAIN "$ENV_FILE" | cut -d= -f2) =="
```

- [ ] **Step 2：赋可执行 + 语法检查**

Run: `chmod +x deploy/init.sh && bash -n deploy/init.sh`
Expected: 无语法错误

### Task F3：update.sh（一键热更新）

**Files:**
- Create: `deploy/update.sh`

- [ ] **Step 1：编写脚本**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=".env.prod"
COMPOSE="docker compose -f docker-compose.prod.yml --env-file $ENV_FILE"

echo "== 拉取最新代码 =="
if [ -d .git ]; then git pull --ff-only; else echo "非 git 仓库，跳过 pull（请先同步代码）"; fi

echo "== 备份（更新前） =="
bash deploy/backup.sh || echo "备份脚本缺失/失败，继续更新"

echo "== 构建镜像（仅变更层重建） =="
$COMPOSE build

echo "== 迁移数据库 =="
$COMPOSE up -d postgres redis
$COMPOSE run --rm web python manage.py migrate --noinput

echo "== 滚动重建服务（不中断依赖） =="
$COMPOSE up -d --no-deps --build web daphne celery beat collector
$COMPOSE exec -T web python manage.py collectstatic --noinput || true

echo "== 清理悬空镜像 =="
docker image prune -f
echo "== 热更新完成 =="
```

- [ ] **Step 2：赋可执行 + 语法检查**

Run: `chmod +x deploy/update.sh && bash -n deploy/update.sh`
Expected: 无语法错误

### Task F4：backup.sh / restore.sh

**Files:**
- Create: `deploy/backup.sh`
- Create: `deploy/restore.sh`

- [ ] **Step 1：backup.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=".env.prod"
COMPOSE="docker compose -f docker-compose.prod.yml --env-file $ENV_FILE"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="backups"; mkdir -p "$OUT"

echo "备份 PostgreSQL → $OUT/db-$TS.sql.gz"
$COMPOSE exec -T postgres pg_dump -U quanly quanly | gzip > "$OUT/db-$TS.sql.gz"

echo "备份数据卷(influxdb/media)"
docker run --rm -v quanly_influx-data:/data -v "$PWD/$OUT":/backup alpine \
  tar czf "/backup/influx-$TS.tar.gz" -C /data . || true

# 仅保留最近 14 份
ls -1t "$OUT"/db-*.sql.gz | tail -n +15 | xargs -r rm -f
echo "备份完成: $TS"
```

- [ ] **Step 2：restore.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=".env.prod"
COMPOSE="docker compose -f docker-compose.prod.yml --env-file $ENV_FILE"
DB_DUMP="${1:-}"
[ -z "$DB_DUMP" ] && { echo "用法: restore.sh backups/db-YYYYmmdd-HHMMSS.sql.gz"; exit 1; }
[ -f "$DB_DUMP" ] || { echo "找不到: $DB_DUMP"; exit 1; }

read -rp "将覆盖当前数据库，确认？(yes/N) " ok
[ "$ok" = "yes" ] || { echo "已取消"; exit 0; }

echo "恢复数据库 from $DB_DUMP"
gunzip -c "$DB_DUMP" | $COMPOSE exec -T postgres psql -U quanly quanly
echo "恢复完成"
```

- [ ] **Step 3：赋可执行 + 语法检查**

Run: `chmod +x deploy/backup.sh deploy/restore.sh && bash -n deploy/backup.sh && bash -n deploy/restore.sh`
Expected: 无语法错误

### Task F5：docker-compose.prod.yml 补齐服务

**Files:**
- Modify: `docker-compose.prod.yml`

- [ ] **Step 1：新增/确认服务**

确保包含：`caddy`（挂 `Caddyfile`、`caddy_data` 卷做证书持久化、映射 80/443）、`web`(gunicorn)、`daphne`(WS)、`celery`、`beat`、`collector`(run_collector)、`private_ws`(run_private_ws)、`redis`、`postgres`、`influxdb`。各服务 `env_file: .env.prod`。新增 `private_ws` 命令：`python manage.py run_private_ws --env sim`（可按需再起一个 live）。

- [ ] **Step 2：配置校验**

Run: `docker compose -f docker-compose.prod.yml --env-file .env.prod config -q`
Expected: 无错误（需先有 .env.prod；本地校验可用占位 .env.prod）

- [ ] **Step 3：最终快照打包**

```bash
cd /c/App/Project && tar czf quanly-p8-done-$(date +%Y%m%d-%H%M%S).tar.gz quanly
```

---

## 自检结论

- **Spec 覆盖**：块 A（A1-A10）覆盖去 mock、私有 WS、REST 同步、reconcile、engine 简化；块 B/C 覆盖行情选择器与 Glass 组件族；块 D 覆盖回测真实 K 线、C2C 删除、理财真实、去硬编码交易对；块 E 覆盖 loading/toast/错误透传；块 F 覆盖 init/update/backup/restore/Caddy/compose。spec 十条决策与六块全部有对应 Task。
- **依赖顺序**：A7（删 mockfeed）显式依赖 D1（回测改真实）；B 依赖 C1（GlassSelect 样式约定）。执行顺序建议：A1-A6 → A8-A10 → D1 → A7 → D2-D5 → C → B → E → F。
- **类型一致**：sync.py 的 `upsert_balances/upsert_positions/upsert_order/full_sync` 在 run_private_ws、sync_views、tasks 中签名一致；adapter 需补 `_decrypt_keys` 与 `parse_ws_*`（A8 Step 6 标注）。前端组件统一 `modelValue`+`update:modelValue`。
- **验证方式**：后端 pytest + monkeypatch + Django check + grep；前端 `npm run build`（vue-tsc）+ 浏览器目视。
