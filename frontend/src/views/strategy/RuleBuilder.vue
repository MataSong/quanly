<template>
  <div class="rule-builder">
    <!-- 买入条件组 -->
    <div class="rule-group">
      <div class="rule-group-head">
        <span class="rule-group-title">{{ t("strategy.buyConditions") }}</span>
        <el-radio-group v-model="local.buy.logic" size="small">
          <el-radio-button value="and">{{ t("strategy.logicAnd") }}</el-radio-button>
          <el-radio-button value="or">{{ t("strategy.logicOr") }}</el-radio-button>
        </el-radio-group>
      </div>
      <div
        v-for="(cond, ci) in local.buy.conditions"
        :key="`buy-${ci}`"
        class="cond-row"
      >
        <!-- 左指标 -->
        <div class="cond-side">
          <el-select v-model="cond.left.ind" size="small" class="ind-select" @change="onLeftIndChange(cond)">
            <el-option v-for="o in IND_OPTIONS" :key="o.value" :value="o.value" :label="t(o.label)" />
          </el-select>
          <el-input-number
            v-if="hasPeriod(cond.left.ind)"
            v-model="cond.left.period"
            :min="1"
            size="small"
            controls-position="right"
            class="param-num"
            :placeholder="t('strategy.period')"
          />
          <template v-if="cond.left.ind === 'MACD'">
            <el-input-number v-model="cond.left.fast" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdFast')" />
            <el-input-number v-model="cond.left.slow" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdSlow')" />
            <el-input-number v-model="cond.left.signal" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdSignal')" />
            <el-select v-model="cond.left.line" size="small" class="line-select">
              <el-option value="macd" :label="t('strategy.macdLineMacd')" />
              <el-option value="signal" :label="t('strategy.macdLineSignal')" />
            </el-select>
          </template>
        </div>

        <!-- 运算符 -->
        <el-select v-model="cond.op" size="small" class="op-select">
          <el-option v-for="o in OP_OPTIONS" :key="o.value" :value="o.value" :label="t(o.label)" />
        </el-select>

        <!-- 右值:指标或常量 -->
        <div class="cond-side">
          <el-select v-model="cond.rightKind" size="small" class="kind-select" @change="onRightKindChange(cond)">
            <el-option value="ind" :label="t('strategy.rightInd')" />
            <el-option value="const" :label="t('strategy.rightConst')" />
          </el-select>
          <template v-if="cond.rightKind === 'const'">
            <el-input-number v-model="cond.constValue" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.constValue')" />
          </template>
          <template v-else>
            <el-select v-model="cond.right.ind" size="small" class="ind-select" @change="onRightIndChange(cond)">
              <el-option v-for="o in IND_OPTIONS" :key="o.value" :value="o.value" :label="t(o.label)" />
            </el-select>
            <el-input-number
              v-if="hasPeriod(cond.right.ind)"
              v-model="cond.right.period"
              :min="1"
              size="small"
              controls-position="right"
              class="param-num"
              :placeholder="t('strategy.period')"
            />
            <template v-if="cond.right.ind === 'MACD'">
              <el-input-number v-model="cond.right.fast" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdFast')" />
              <el-input-number v-model="cond.right.slow" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdSlow')" />
              <el-input-number v-model="cond.right.signal" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdSignal')" />
              <el-select v-model="cond.right.line" size="small" class="line-select">
                <el-option value="macd" :label="t('strategy.macdLineMacd')" />
                <el-option value="signal" :label="t('strategy.macdLineSignal')" />
              </el-select>
            </template>
          </template>
        </div>

        <el-button size="small" type="danger" plain :icon="Delete" @click="removeCond('buy', ci)" />
      </div>
      <el-button size="small" :icon="Plus" @click="addCond('buy')">{{ t("strategy.addCondition") }}</el-button>
    </div>

    <!-- 卖出条件组 -->
    <div class="rule-group">
      <div class="rule-group-head">
        <span class="rule-group-title">{{ t("strategy.sellConditions") }}</span>
        <el-radio-group v-model="local.sell.logic" size="small">
          <el-radio-button value="and">{{ t("strategy.logicAnd") }}</el-radio-button>
          <el-radio-button value="or">{{ t("strategy.logicOr") }}</el-radio-button>
        </el-radio-group>
      </div>
      <div
        v-for="(cond, ci) in local.sell.conditions"
        :key="`sell-${ci}`"
        class="cond-row"
      >
        <div class="cond-side">
          <el-select v-model="cond.left.ind" size="small" class="ind-select" @change="onLeftIndChange(cond)">
            <el-option v-for="o in IND_OPTIONS" :key="o.value" :value="o.value" :label="t(o.label)" />
          </el-select>
          <el-input-number
            v-if="hasPeriod(cond.left.ind)"
            v-model="cond.left.period"
            :min="1"
            size="small"
            controls-position="right"
            class="param-num"
            :placeholder="t('strategy.period')"
          />
          <template v-if="cond.left.ind === 'MACD'">
            <el-input-number v-model="cond.left.fast" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdFast')" />
            <el-input-number v-model="cond.left.slow" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdSlow')" />
            <el-input-number v-model="cond.left.signal" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdSignal')" />
            <el-select v-model="cond.left.line" size="small" class="line-select">
              <el-option value="macd" :label="t('strategy.macdLineMacd')" />
              <el-option value="signal" :label="t('strategy.macdLineSignal')" />
            </el-select>
          </template>
        </div>

        <el-select v-model="cond.op" size="small" class="op-select">
          <el-option v-for="o in OP_OPTIONS" :key="o.value" :value="o.value" :label="t(o.label)" />
        </el-select>

        <div class="cond-side">
          <el-select v-model="cond.rightKind" size="small" class="kind-select" @change="onRightKindChange(cond)">
            <el-option value="ind" :label="t('strategy.rightInd')" />
            <el-option value="const" :label="t('strategy.rightConst')" />
          </el-select>
          <template v-if="cond.rightKind === 'const'">
            <el-input-number v-model="cond.constValue" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.constValue')" />
          </template>
          <template v-else>
            <el-select v-model="cond.right.ind" size="small" class="ind-select" @change="onRightIndChange(cond)">
              <el-option v-for="o in IND_OPTIONS" :key="o.value" :value="o.value" :label="t(o.label)" />
            </el-select>
            <el-input-number
              v-if="hasPeriod(cond.right.ind)"
              v-model="cond.right.period"
              :min="1"
              size="small"
              controls-position="right"
              class="param-num"
              :placeholder="t('strategy.period')"
            />
            <template v-if="cond.right.ind === 'MACD'">
              <el-input-number v-model="cond.right.fast" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdFast')" />
              <el-input-number v-model="cond.right.slow" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdSlow')" />
              <el-input-number v-model="cond.right.signal" :min="1" size="small" controls-position="right" class="param-num" :placeholder="t('strategy.macdSignal')" />
              <el-select v-model="cond.right.line" size="small" class="line-select">
                <el-option value="macd" :label="t('strategy.macdLineMacd')" />
                <el-option value="signal" :label="t('strategy.macdLineSignal')" />
              </el-select>
            </template>
          </template>
        </div>

        <el-button size="small" type="danger" plain :icon="Delete" @click="removeCond('sell', ci)" />
      </div>
      <el-button size="small" :icon="Plus" @click="addCond('sell')">{{ t("strategy.addCondition") }}</el-button>
    </div>

    <!-- 止盈止损 -->
    <div class="rule-group">
      <div class="rule-group-head">
        <span class="rule-group-title">{{ t("strategy.riskTitle") }}</span>
      </div>
      <div class="risk-row">
        <div class="risk-field">
          <span class="risk-label">{{ t("strategy.takeProfitPct") }}</span>
          <el-input-number
            v-model="local.risk.take_profit_pct"
            :min="0"
            :step="0.5"
            size="small"
            controls-position="right"
            :placeholder="t('strategy.riskHint')"
            class="risk-num"
          />
        </div>
        <div class="risk-field">
          <span class="risk-label">{{ t("strategy.stopLossPct") }}</span>
          <el-input-number
            v-model="local.risk.stop_loss_pct"
            :min="0"
            :step="0.5"
            size="small"
            controls-position="right"
            :placeholder="t('strategy.riskHint')"
            class="risk-num"
          />
        </div>
      </div>
    </div>

    <!-- 下单量 -->
    <div class="rule-group">
      <div class="rule-group-head">
        <span class="rule-group-title">{{ t("strategy.orderSize") }}</span>
      </div>
      <el-input v-model="local.sz" size="small" placeholder="0.001" class="sz-input" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Delete, Plus } from "@element-plus/icons-vue";

const { t } = useI18n();

// ── Types ───────────────────────────────────────────────────────────────────
type IndName = "MA" | "EMA" | "RSI" | "MACD" | "price" | "volume";
type OpName = "cross_above" | "cross_below" | ">" | "<" | ">=" | "<=";
type Logic = "and" | "or";

interface Operand {
  ind?: IndName;
  period?: number;
  fast?: number;
  slow?: number;
  signal?: number;
  line?: "macd" | "signal";
  const?: number;
}

interface RuleCondition {
  left: Operand;
  op: OpName;
  right: Operand;
}

interface RuleGroup {
  logic: Logic;
  conditions: RuleCondition[];
}

export interface RuleConfig {
  buy: RuleGroup;
  sell: RuleGroup;
  risk: { take_profit_pct?: number; stop_loss_pct?: number };
  sz: string;
}

// Local (editable) shapes carry UI-only fields (rightKind/constValue) that are
// stripped when emitting the clean rule_config.
interface LocalOperand {
  ind: IndName;
  period?: number;
  fast?: number;
  slow?: number;
  signal?: number;
  line?: "macd" | "signal";
}
interface LocalCondition {
  left: LocalOperand;
  op: OpName;
  rightKind: "ind" | "const";
  right: LocalOperand;
  constValue: number;
}
interface LocalGroup {
  logic: Logic;
  conditions: LocalCondition[];
}
interface LocalConfig {
  buy: LocalGroup;
  sell: LocalGroup;
  risk: { take_profit_pct?: number; stop_loss_pct?: number };
  sz: string;
}

const IND_OPTIONS: { value: IndName; label: string }[] = [
  { value: "MA", label: "strategy.indMA" },
  { value: "EMA", label: "strategy.indEMA" },
  { value: "RSI", label: "strategy.indRSI" },
  { value: "MACD", label: "strategy.indMACD" },
  { value: "price", label: "strategy.indPrice" },
  { value: "volume", label: "strategy.indVolume" },
];

const OP_OPTIONS: { value: OpName; label: string }[] = [
  { value: "cross_above", label: "strategy.opCrossAbove" },
  { value: "cross_below", label: "strategy.opCrossBelow" },
  { value: ">", label: "strategy.opGt" },
  { value: "<", label: "strategy.opLt" },
  { value: ">=", label: "strategy.opGte" },
  { value: "<=", label: "strategy.opLte" },
];

function hasPeriod(ind: IndName | undefined): boolean {
  return ind === "MA" || ind === "EMA" || ind === "RSI";
}

// ── v-model ─────────────────────────────────────────────────────────────────
const props = defineProps<{ modelValue: RuleConfig }>();
const emit = defineEmits<{ (e: "update:modelValue", v: RuleConfig): void }>();

function newLocalOperand(ind: IndName = "MA"): LocalOperand {
  const op: LocalOperand = { ind };
  if (hasPeriod(ind)) op.period = 14;
  if (ind === "MACD") {
    op.fast = 12;
    op.slow = 26;
    op.signal = 9;
    op.line = "macd";
  }
  return op;
}

/** Parse an incoming rule_config operand into a LocalOperand + detect const. */
function parseOperand(raw: unknown): { operand: LocalOperand; isConst: boolean; constValue: number } {
  const o = (raw ?? {}) as Operand;
  if (o.const !== undefined && o.ind === undefined) {
    return { operand: newLocalOperand("MA"), isConst: true, constValue: Number(o.const) };
  }
  const ind = (o.ind ?? "MA") as IndName;
  const operand: LocalOperand = { ind };
  if (hasPeriod(ind)) operand.period = o.period ?? 14;
  if (ind === "MACD") {
    operand.fast = o.fast ?? 12;
    operand.slow = o.slow ?? 26;
    operand.signal = o.signal ?? 9;
    operand.line = o.line ?? "macd";
  }
  return { operand, isConst: false, constValue: 0 };
}

function parseGroup(raw: unknown, defaultLogic: Logic): LocalGroup {
  const g = (raw ?? {}) as { logic?: Logic; conditions?: unknown[] };
  const conditions = Array.isArray(g.conditions) ? g.conditions : [];
  return {
    logic: g.logic === "or" || g.logic === "and" ? g.logic : defaultLogic,
    conditions: conditions.map((c) => {
      const cc = (c ?? {}) as RuleCondition;
      const left = parseOperand(cc.left);
      const right = parseOperand(cc.right);
      return {
        left: left.operand,
        op: (cc.op ?? "cross_above") as OpName,
        rightKind: right.isConst ? "const" : "ind",
        right: right.operand,
        constValue: right.constValue,
      } as LocalCondition;
    }),
  };
}

function toLocal(mv: RuleConfig): LocalConfig {
  return {
    buy: parseGroup(mv?.buy, "and"),
    sell: parseGroup(mv?.sell, "or"),
    risk: {
      take_profit_pct: mv?.risk?.take_profit_pct ?? undefined,
      stop_loss_pct: mv?.risk?.stop_loss_pct ?? undefined,
    },
    sz: mv?.sz ?? "0.001",
  };
}

const local = reactive<LocalConfig>(toLocal(props.modelValue));

// ── Operand cleanup on indicator change ───────────────────────────────────────
function normalizeOperand(op: LocalOperand) {
  if (hasPeriod(op.ind)) {
    if (op.period === undefined) op.period = 14;
  } else {
    delete op.period;
  }
  if (op.ind === "MACD") {
    if (op.fast === undefined) op.fast = 12;
    if (op.slow === undefined) op.slow = 26;
    if (op.signal === undefined) op.signal = 9;
    if (op.line === undefined) op.line = "macd";
  } else {
    delete op.fast;
    delete op.slow;
    delete op.signal;
    delete op.line;
  }
}

function onLeftIndChange(cond: LocalCondition) {
  normalizeOperand(cond.left);
}
function onRightIndChange(cond: LocalCondition) {
  normalizeOperand(cond.right);
}
function onRightKindChange(cond: LocalCondition) {
  if (cond.rightKind === "ind") normalizeOperand(cond.right);
}

// ── Add / remove conditions ───────────────────────────────────────────────────
function addCond(group: "buy" | "sell") {
  local[group].conditions.push({
    left: newLocalOperand("MA"),
    op: "cross_above",
    rightKind: "ind",
    right: newLocalOperand("MA"),
    constValue: 0,
  });
}
function removeCond(group: "buy" | "sell", idx: number) {
  local[group].conditions.splice(idx, 1);
}

// ── Emit clean rule_config ────────────────────────────────────────────────────
function cleanOperand(op: LocalOperand): Operand {
  const out: Operand = { ind: op.ind };
  if (hasPeriod(op.ind)) out.period = op.period ?? 14;
  if (op.ind === "MACD") {
    out.fast = op.fast ?? 12;
    out.slow = op.slow ?? 26;
    out.signal = op.signal ?? 9;
    out.line = op.line ?? "macd";
  }
  return out;
}

function cleanGroup(g: LocalGroup): RuleGroup {
  return {
    logic: g.logic,
    conditions: g.conditions.map((c) => ({
      left: cleanOperand(c.left),
      op: c.op,
      right: c.rightKind === "const" ? { const: c.constValue } : cleanOperand(c.right),
    })),
  };
}

function buildConfig(): RuleConfig {
  const risk: { take_profit_pct?: number; stop_loss_pct?: number } = {};
  if (local.risk.take_profit_pct != null) risk.take_profit_pct = local.risk.take_profit_pct;
  if (local.risk.stop_loss_pct != null) risk.stop_loss_pct = local.risk.stop_loss_pct;
  return {
    buy: cleanGroup(local.buy),
    sell: cleanGroup(local.sell),
    risk,
    sz: local.sz?.trim() ? local.sz.trim() : "0.001",
  };
}

// Emit on every local change.
watch(
  local,
  () => {
    emit("update:modelValue", buildConfig());
  },
  { deep: true },
);

// Re-hydrate when parent replaces modelValue wholesale (e.g. openEdit reset).
watch(
  () => props.modelValue,
  (mv) => {
    const built = buildConfig();
    if (JSON.stringify(built) === JSON.stringify(mv)) return;
    const next = toLocal(mv);
    local.buy = next.buy;
    local.sell = next.sell;
    local.risk = next.risk;
    local.sz = next.sz;
  },
);
</script>

<style scoped lang="scss">
@use "@/styles/mixins" as *;

.rule-builder {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
}

.rule-group {
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  background: var(--gray-50);
}

.rule-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.rule-group-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--gray-700);
}

.cond-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  padding: var(--space-2);
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: var(--radius-sm);
}

.cond-side {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.ind-select { width: 110px; }
.op-select { width: 110px; }
.kind-select { width: 90px; }
.line-select { width: 110px; }
.param-num { width: 96px; }
.risk-num { width: 160px; }
.sz-input { width: 160px; }

.risk-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
}

.risk-field {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.risk-label {
  font-size: var(--font-size-sm);
  color: var(--gray-600);
  white-space: nowrap;
}

// 手机端:条件行内元素竖排
@include mobile {
  .cond-row {
    flex-direction: column;
    align-items: stretch;
  }
  .cond-side {
    flex-direction: column;
    align-items: stretch;
  }
  .ind-select,
  .op-select,
  .kind-select,
  .line-select,
  .param-num,
  .risk-num,
  .sz-input {
    width: 100%;
  }
  .risk-row {
    flex-direction: column;
  }
  .risk-field {
    justify-content: space-between;
  }
}
</style>
