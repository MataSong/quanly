# 删除理财板块(保留划转与底层封装)

日期:2026-08-11

## 目标

从前端和后端删除「理财」功能(活期/定期/双币/Staking/借贷 的申购、赎回、持仓展示),同时:

- 保留「划转 Transfer」功能(资金账户间划转),它目前与理财同在 `apps/finance` app / `api/finance.ts` 中,**原地保留**。
- 保留交易所底层封装(`exchanges/okx/adapter.py` 的储蓄/划转方法),它们与 finance app 解耦、可复用,**完全不动**。

## 范围决策(已与用户确认)

1. 删除范围**只含理财,不含划转**。
2. 划转**原地保留**在 `finance` app / `finance.ts`,不迁出。
3. Dashboard 的「理财价值」「借贷价值」两张卡片**一并删除**,`assets` 汇总不再聚合理财。

## 后端改动

### 1. `apps/finance/models.py`
- 删除 `FinanceProduct`、`FinanceHolding`。
- 保留 `Transfer`。

### 2. 新增 migration
- 删除 `financeholding`、`financeproduct` 两张表。
- 删除顺序:先 `FinanceHolding`(其外键指向 `FinanceProduct`),再 `FinanceProduct`。

### 3. `apps/finance/views.py`
- 删除 `products`、`holdings`、`subscribe`、`redeem`。
- 删除仅理财使用的 `_okx` 辅助函数。
- 保留 `transfer`、`transfers`。实现时确认这两个 view 内部各自创建 adapter,不依赖被删除的 `_okx`;若它们也依赖 `_okx`,则保留一份等价的 adapter 获取逻辑。

### 4. `apps/finance/urls.py`
- 删除 `finance/products`、`finance/holdings`、`finance/subscribe`、`finance/redeem/<pk>`。
- 保留 `finance/transfer`、`finance/transfers`。

### 5. `apps/finance/test_finance.py`
- 删除 `test_products_from_okx`、`test_subscribe_and_redeem`、`test_subscribe_requires_credential`。
- 保留并调整 `test_transfer`:`_FakeAdapter` 只需保留 `transfer` 方法。

### 6. `apps/assets/service.py`
- 移除 `from apps.finance.models import FinanceHolding` 及其聚合循环。
- 从返回值删除 `finance_value`、`loan_value`。
- `total_equity` 改为 `spot_value + swap_value`。
- 更新文件顶部 docstring(移除「理财/借贷由 FinanceHolding 聚合」的描述)。

### 7. `config/urls.py`
- 不变:仍 `include("apps.finance.urls")`(划转仍在 finance app)。

### 不动
- `apps/exchanges/okx/adapter.py`:`get_savings_products`、`subscribe_savings`、`redeem_savings`、`get_savings`、`transfer` 全部保留。

## 前端改动

### 8. `views/Finance.vue`
- 删除整个文件。

### 9. `router/index.ts`
- 删除 `/finance` 路由,保留 `/transfer`。

### 10. `layouts/GlassLayout.vue`
- 删除菜单项 `{ path: "/finance", key: "nav.finance" }`,保留 `/transfer`。

### 11. `api/finance.ts`
- 删除 `products`、`holdings`、`subscribe`、`redeem`。
- 保留 `transfer`、`transfers`。

### 12. `views/Dashboard.vue`
- 删除「理财价值」(`dashboard.financeValue` / `sum?.finance_value`)与「借贷价值」(`dashboard.loanValue` / `sum?.loan_value`)两张卡片。卡片从 6 张变 4 张。

### 13. `views/Transfer.vue`
- 逻辑不改。它复用 `finance.ccy`、`finance.amount` 两个 i18n key,须确保这两个 key 在下一步 i18n 清理中被保留。

### 14. i18n(`zh-CN.ts` / `en-US.ts`)
- 删除理财专属 key:`nav.finance`、`dashboard.financeValue`、`dashboard.loanValue`,以及 `finance` 命名空间下仅被 `Finance.vue` 引用的 key。
- **保留** `finance.ccy`、`finance.amount`(划转 `Transfer.vue` 在用)。
- **保留** `transfer.*`、`nav.transfer`。
- 实现时逐个核对 `finance.*` key 的引用来源,只删仅 Finance.vue 使用的。

## 数据流影响

- 资产汇总:`total_equity = spot_value + swap_value`,不再含理财;summary 返回体去掉 `finance_value`、`loan_value`。
- Dashboard:6 张卡 → 4 张卡。
- 划转链路完全不受影响:`Transfer.vue` → `finance.ts::transfer/transfers` → `finance/views.py::transfer/transfers` → adapter `transfer`。

## 验证

### 后端
- `pytest`:finance 的划转测试(`test_transfer`)、assets 测试通过。
- `migrate`:迁移正常执行,理财两表被删除。
- 全局搜索确认无残留对 `FinanceProduct` / `FinanceHolding` 的 import 或引用(底层 adapter 方法名不算)。

### 前端
- `npm run build` 通过:无对已删除 `Finance.vue`、`finance.ts` 方法、或已删除 i18n key 的悬空引用。
- 启动后手动核对:
  - 侧边菜单无「理财」项,仍有「划转」。
  - Dashboard 显示 4 张卡(可用、冻结、现货价值、合约价值),无理财/借贷卡。
  - 划转页面正常:可提交划转、记录列表正常显示。
