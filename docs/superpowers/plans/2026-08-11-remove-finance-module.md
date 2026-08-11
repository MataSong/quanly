# 删除理财板块 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从前后端删除「理财」功能(理财产品/持仓/申购/赎回),保留「划转 Transfer」与交易所底层封装。

**Architecture:** 后端 `apps/finance` app 里删除理财相关 model/view/url/test,保留 `Transfer` model 及其 view/url 和它依赖的 `_okx` 辅助函数;`apps/assets/service.py` 停止聚合理财持仓。前端删除 `Finance.vue`、路由、菜单、`finance.ts` 的理财方法、Dashboard 两张卡片和理财专属 i18n key。交易所适配器(`exchanges/okx/adapter.py`)完全不动。

**Tech Stack:** Django 5.2 + DRF + pytest(后端);Vue 3 + vue-router + vue-i18n + Vite(前端)。

**重要修正(相对 spec):** spec 说"删除仅理财使用的 `_okx`",但核实后 `transfer` view(保留项)也依赖 `_okx`(views.py:120)。因此 **`_okx` 必须保留**。此外发现 spec 未提及的两处理财残留:`trading/test_okx_integration.py::test_finance_subscribe_okx_mode_calls_adapter` 也测理财申购,需删除。

---

### Task 1: 删除后端理财 view / url,保留划转与 `_okx`

**Files:**
- Modify: `backend/apps/finance/views.py`
- Modify: `backend/apps/finance/urls.py`
- Test: `backend/apps/finance/test_finance.py`

- [ ] **Step 1: 改写 `test_finance.py` 为仅覆盖划转(先让理财测试消失,划转测试保留)**

将 `backend/apps/finance/test_finance.py` 整个文件替换为:

```python
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.credentials.models import ExchangeCredential
from apps.finance import views as finance_views


class _FakeAdapter:
    def transfer(self, ccy, amount, **kw):
        return {"ok": True}


@pytest.fixture
def auth(db, monkeypatch):
    u = get_user_model().objects.create_user("fin", password="pass12345")
    ExchangeCredential.objects.create(
        user=u, env="sim", exchange="okx",
        api_key="k", secret_enc="s", passphrase_enc="p",
    )
    monkeypatch.setattr(finance_views, "_okx", lambda user, env: _FakeAdapter())
    c = APIClient()
    c.force_authenticate(u)
    return c, u


def test_transfer(auth):
    c, u = auth
    r = c.post(
        "/api/finance/transfer",
        {"env": "sim", "ccy": "USDT", "amount": "500", "from_acct": "trading", "to_acct": "funding"},
        format="json",
    )
    assert r.status_code == 201
    assert len(c.get("/api/finance/transfers?env=sim").data) == 1
```

- [ ] **Step 2: 运行测试,确认因 view 仍引用已删 model 之外的原因不失败(此时 view 未改,应通过)**

Run: `cd backend && python -m pytest apps/finance/test_finance.py -v`
Expected: PASS(`test_transfer` 通过;理财测试已从文件移除)

- [ ] **Step 3: 删除 `views.py` 中的理财 view,保留 `_okx`/`transfer`/`transfers`**

将 `backend/apps/finance/views.py` 整个文件替换为:

```python
from decimal import Decimal

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Transfer

D = Decimal


def _okx(user, env):
    """取该用户该环境的 OKX 适配器(用其 credential);无则 None。"""
    from apps.credentials.models import Env, ExchangeCredential
    from apps.exchanges.factory import AdapterFactory

    cred = ExchangeCredential.objects.filter(user=user, env=env, exchange="okx").first()
    if not cred:
        return None
    return AdapterFactory.create("okx", Env.SIM if env == "sim" else Env.LIVE, cred)


@api_view(["POST"])
def transfer(request):
    env = request.data.get("env", "sim")
    ccy = request.data["ccy"]
    amount = D(str(request.data["amount"]))
    adapter = _okx(request.user, env)
    if not adapter:
        return Response({"detail": "未配置 OKX 凭证"}, status=400)
    try:
        adapter.transfer(ccy, amount)
    except Exception as e:  # noqa: BLE001
        return Response({"detail": f"OKX 划转失败: {e}"}, status=502)
    t = Transfer.objects.create(
        user=request.user,
        env=env,
        ccy=ccy,
        amount=amount,
        from_acct=request.data.get("from_acct", "trading"),
        to_acct=request.data.get("to_acct", "funding"),
    )
    return Response({"id": t.id}, status=201)


@api_view(["GET"])
def transfers(request):
    env = request.query_params.get("env", "sim")
    qs = Transfer.objects.filter(user=request.user, env=env)[:100]
    return Response(
        [
            {
                "id": t.id, "ccy": t.ccy, "amount": float(t.amount),
                "from_acct": t.from_acct, "to_acct": t.to_acct,
                "created_at": t.created_at.isoformat(),
            }
            for t in qs
        ]
    )
```

- [ ] **Step 4: 删除 `urls.py` 中的理财路由**

将 `backend/apps/finance/urls.py` 整个文件替换为:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("finance/transfer", views.transfer),
    path("finance/transfers", views.transfers),
]
```

- [ ] **Step 5: 运行 finance 测试确认划转仍通过**

Run: `cd backend && python -m pytest apps/finance/test_finance.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/apps/finance/views.py backend/apps/finance/urls.py backend/apps/finance/test_finance.py
git commit -m "refactor: 删除后端理财 view/url,保留划转"
```

---

### Task 2: 删除理财 model 并生成删表迁移

**Files:**
- Modify: `backend/apps/finance/models.py`
- Create: `backend/apps/finance/migrations/0002_delete_finance_models.py`(由 makemigrations 生成)

- [ ] **Step 1: 删除 `models.py` 中的 `FinanceProduct`、`FinanceHolding`,保留 `Transfer`**

将 `backend/apps/finance/models.py` 整个文件替换为:

```python
from django.conf import settings
from django.db import models

from apps.credentials.models import Env


class Transfer(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    env = models.CharField(max_length=4, choices=Env.choices)
    ccy = models.CharField(max_length=16)
    amount = models.DecimalField(max_digits=24, decimal_places=8)
    from_acct = models.CharField(max_length=24)  # trading/funding/earn
    to_acct = models.CharField(max_length=24)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
```

- [ ] **Step 2: 生成迁移**

Run: `cd backend && python manage.py makemigrations finance`
Expected: 生成 `0002_delete_financeholding_delete_financeproduct.py`(或类似名),含两个 `DeleteModel`(先 `FinanceHolding` 再 `FinanceProduct`)。若文件名不同,以实际生成为准。

- [ ] **Step 3: 应用迁移**

Run: `cd backend && python manage.py migrate finance`
Expected: 迁移成功,`finance_financeholding`、`finance_financeproduct` 两表被删除。

- [ ] **Step 4: 运行 finance 测试确认无回归**

Run: `cd backend && python -m pytest apps/finance/ -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/apps/finance/models.py backend/apps/finance/migrations/
git commit -m "refactor: 删除理财 model 并生成删表迁移"
```

---

### Task 3: assets 汇总停止聚合理财

**Files:**
- Modify: `backend/apps/assets/service.py`
- Test: `backend/apps/assets/test_assets.py`(核对现有断言)

- [ ] **Step 1: 检查现有 assets 测试对 finance_value/loan_value/total_equity 的断言**

Run: `cd backend && grep -n "finance_value\|loan_value\|total_equity" apps/assets/test_assets.py`
Expected: 列出引用行。若测试断言包含 `finance_value`/`loan_value`,在 Step 3 一并调整;若断言 `total_equity` 含理财,改为不含理财的期望值。

- [ ] **Step 2: 改写 `service.py`,移除理财聚合**

将 `backend/apps/assets/service.py` 整个文件替换为:

```python
"""资产聚合:把现货余额、合约持仓折算成统一净值视图。

净值折算用 Redis 缓存的真实 OKX 最新价;读不到价则该项折 0(不再有假数据兜底)。
"""
from decimal import Decimal

from apps.trading.models import Balance, Position, PosSide
from apps.trading.prices import get_last_price

D = Decimal


def _price(symbol: str) -> Decimal:
    p = get_last_price(symbol)
    return D(str(p)) if p is not None else D("0")


def summarize(user, env: str) -> dict:
    # 现货:各币种折 USDT
    spot_value = D("0")
    available_usdt = D("0")
    for bal in Balance.objects.filter(user=user, env=env):
        if bal.ccy == "USDT":
            val = bal.total
            available_usdt += (bal.total - bal.frozen)
        else:
            val = bal.total * _price(f"{bal.ccy}-USDT")
        spot_value += val

    # 合约:保证金 + 未实现盈亏
    swap_margin = D("0")
    upl = D("0")
    positions_dist = []
    for pos in Position.objects.filter(user=user, env=env, qty__gt=0):
        px = _price(pos.symbol)
        if pos.pos_side == PosSide.LONG:
            p_upl = (px - pos.avg_px) * pos.qty
        else:
            p_upl = (pos.avg_px - px) * pos.qty
        notional = px * pos.qty
        swap_margin += pos.margin
        upl += p_upl
        positions_dist.append(
            {
                "symbol": pos.symbol,
                "pos_side": pos.pos_side,
                "notional": float(notional),
                "upl": float(p_upl),
            }
        )

    swap_value = swap_margin + upl
    frozen = swap_margin

    total_equity = spot_value + swap_value

    return {
        "env": env,
        "total_equity": float(total_equity),
        "available": float(available_usdt),
        "frozen": float(frozen),
        "upl": float(upl),
        "spot_value": float(spot_value),
        "swap_value": float(swap_value),
        "positions_dist": positions_dist,
    }
```

- [ ] **Step 3: 若 Step 1 发现测试引用了已删字段,调整测试**

如果 `apps/assets/test_assets.py` 断言了 `r.data["finance_value"]` / `r.data["loan_value"]`,删除这些断言;如果断言 `total_equity` 期望值含理财持仓,改为只含现货+合约的期望值。如果 Step 1 未发现相关断言,跳过本步。

- [ ] **Step 4: 运行 assets 测试**

Run: `cd backend && python -m pytest apps/assets/ -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/apps/assets/service.py backend/apps/assets/test_assets.py
git commit -m "refactor: assets 汇总不再聚合理财持仓"
```

---

### Task 4: 删除 trading 集成测试里的理财申购用例

**Files:**
- Modify: `backend/apps/trading/test_okx_integration.py`

- [ ] **Step 1: 删除 `test_finance_subscribe_okx_mode_calls_adapter`**

删除 `backend/apps/trading/test_okx_integration.py` 中从 `@pytest.mark.django_db`(第 34 行上方)到 `test_finance_subscribe_okx_mode_calls_adapter` 函数结尾(第 64 行)的整个测试函数,包括其上方的 `@pytest.mark.django_db` 装饰器。其余测试保留不动。

- [ ] **Step 2: 运行该文件确认无对 finance.views 理财接口的引用**

Run: `cd backend && python -m pytest apps/trading/test_okx_integration.py -v`
Expected: PASS(无 `test_finance_subscribe_okx_mode_calls_adapter`,其余测试通过)

- [ ] **Step 3: 全局确认后端无理财 model 残留引用**

Run: `cd backend && grep -rn "FinanceProduct\|FinanceHolding" apps/ --include=*.py`
Expected: 无输出(适配器方法名 `get_savings_products` 等不含这些标识符,不会命中)。

- [ ] **Step 4: 后端全量测试**

Run: `cd backend && python -m pytest -q`
Expected: PASS(全绿)

- [ ] **Step 5: 提交**

```bash
git add backend/apps/trading/test_okx_integration.py
git commit -m "test: 删除理财申购集成测试用例"
```

---

### Task 5: 删除前端理财 API 方法、页面、路由、菜单

**Files:**
- Modify: `frontend/src/api/finance.ts`
- Delete: `frontend/src/views/Finance.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/GlassLayout.vue`

- [ ] **Step 1: 精简 `api/finance.ts` 只保留划转**

将 `frontend/src/api/finance.ts` 整个文件替换为:

```typescript
import client from "./client";

export const financeApi = {
  transfer: (payload: any) => client.post("/finance/transfer", payload),
  transfers: (env: string) => client.get("/finance/transfers", { params: { env } }),
};
```

- [ ] **Step 2: 删除 Finance.vue**

Run: `git rm frontend/src/views/Finance.vue`
Expected: 文件被删除并 staged。

- [ ] **Step 3: 从路由删除 `/finance`**

在 `frontend/src/router/index.ts` 中删除这一行:

```typescript
        { path: "finance", component: () => import("@/views/Finance.vue") },
```

保留 `{ path: "transfer", component: () => import("@/views/Transfer.vue") }`。

- [ ] **Step 4: 从菜单删除理财项**

在 `frontend/src/layouts/GlassLayout.vue` 中删除这一行:

```typescript
  { path: "/finance", key: "nav.finance" },
```

保留 `{ path: "/transfer", key: "nav.transfer" }`。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/finance.ts frontend/src/router/index.ts frontend/src/layouts/GlassLayout.vue
git commit -m "refactor: 删除前端理财页面/路由/菜单/API"
```

---

### Task 6: 删除 Dashboard 理财/借贷卡片

**Files:**
- Modify: `frontend/src/views/Dashboard.vue`

- [ ] **Step 1: 删除两张卡片的模板块**

在 `frontend/src/views/Dashboard.vue` 的 `<div class="cards">` 内,删除以下两个卡片块:

```html
      <div class="glass card">
        <div class="card-label">{{ $t("dashboard.financeValue") }}</div>
        <div class="card-val">{{ fmt(sum?.finance_value) }}</div>
      </div>
      <div class="glass card">
        <div class="card-label">{{ $t("dashboard.loanValue") }}</div>
        <div class="card-val">{{ fmt(sum?.loan_value) }}</div>
      </div>
```

保留「可用」「冻结」「现货价值」「合约价值」四张卡片。

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/Dashboard.vue
git commit -m "refactor: Dashboard 删除理财/借贷卡片"
```

---

### Task 7: 清理理财专属 i18n key(保留 finance.ccy / finance.amount)

**Files:**
- Modify: `frontend/src/i18n/zh-CN.ts`
- Modify: `frontend/src/i18n/en-US.ts`

- [ ] **Step 1: zh-CN.ts — 删除 nav.finance**

在 `frontend/src/i18n/zh-CN.ts` 的 `nav` 块中删除 `finance: "理财",`,保留 `transfer: "划转",`。

- [ ] **Step 2: zh-CN.ts — 删除 dashboard.financeValue / loanValue**

删除 `dashboard` 块中的 `financeValue: "理财",` 和 `loanValue: "借贷",`。

- [ ] **Step 3: zh-CN.ts — 精简 finance 命名空间,只留划转复用的 ccy/amount**

将 `zh-CN.ts` 中整个 `finance: { ... }` 块替换为:

```typescript
  finance: {
    ccy: "币种",
    amount: "金额",
  },
```

`transfer: { ... }` 块保持不动。

- [ ] **Step 4: en-US.ts — 同样三处清理**

在 `frontend/src/i18n/en-US.ts` 中:
- `nav` 块删除 `finance: "Earn",`(保留 transfer)。
- `dashboard` 块删除 `financeValue: "Earn",` 和 `loanValue: "Loan",`。
- 将整个 `finance: { ... }` 块替换为只保留划转复用的两个 key(用 en-US 现有英文文案):

```typescript
  finance: {
    ccy: "Currency",
    amount: "Amount",
  },
```

> 注:实现时先读 `en-US.ts` 的 `finance` 块,确认 `ccy` / `amount` 的原英文文案并沿用,不要凭空翻译。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/i18n/zh-CN.ts frontend/src/i18n/en-US.ts
git commit -m "refactor: 清理理财专属 i18n key,保留划转复用的 ccy/amount"
```

---

### Task 8: 前端构建验证与手动核对

**Files:** 无(验证任务)

- [ ] **Step 1: 全局搜索确认无悬空引用**

Run: `cd frontend && grep -rn "Finance.vue\|financeApi.products\|financeApi.holdings\|financeApi.subscribe\|financeApi.redeem\|finance.subscribed\|finance.redeemed\|finance.earn\|finance.loan\|finance.products\|finance.myHoldings\|financeValue\|loanValue\|nav.finance\|finance_value\|loan_value" src/`
Expected: 无输出(所有理财专属引用已清除;`finance.ccy`/`finance.amount`/`transfer.*`/`nav.transfer` 不在搜索项内,不受影响)。

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd frontend && npm run build`
Expected: 构建成功,无 TS 报错、无对已删除模块/i18n key 的报错。

- [ ] **Step 3: 手动核对(启动 dev server)**

Run: `cd frontend && npm run dev`
在浏览器中确认:
- 侧边菜单无「理财」项,仍有「划转」。
- Dashboard 显示 4 张卡(可用、冻结、现货价值、合约价值),无理财/借贷卡。
- 打开划转页面:能加载记录列表、能提交划转(如有凭证)、币种/金额字段文案正常显示(验证 `finance.ccy`/`finance.amount` 仍生效)。

若无法在浏览器中运行(无凭证/无后端),明确说明未做浏览器验证,并至少确认 `npm run build` 通过。

- [ ] **Step 4: 提交(若手动核对期间无代码改动则跳过)**

无代码改动则本任务不产生 commit。

---

## 收尾

- [ ] 后端 `python -m pytest -q` 全绿。
- [ ] 前端 `npm run build` 通过。
- [ ] 交易所底层封装 `exchanges/okx/adapter.py` 的储蓄/划转方法未被改动(可 `git diff --stat` 确认该文件不在改动列表中)。
