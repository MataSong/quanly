<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { tradingApi, type OrderPayload } from "@/api/trading";
import client from "@/api/client";
import { useAuth } from "@/stores/auth";
import Pagination from "@/components/Pagination.vue";
import GlassSelect from "@/components/GlassSelect.vue";
import SearchSelect from "@/components/SearchSelect.vue";
import GlassNumber from "@/components/GlassNumber.vue";
import GlassSlider from "@/components/GlassSlider.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { usePagination } from "@/composables/usePagination";
import { useToast } from "@/composables/useToast";

const auth = useAuth();
const { t, te } = useI18n();
const toast = useToast();

function ordTypeLabel(v: string) {
  const k = `trade.ordType.${v}`;
  return te(k) ? t(k) : v;
}
function orderStateLabel(v: string) {
  const k = `trade.orderState.${v}`;
  return te(k) ? t(k) : v;
}

const SYMBOLS = ref<string[]>(["BTC-USDT", "ETH-USDT", "SOL-USDT"]);
const SYMBOLS_BY_TYPE = ref<Record<string, string[]>>({});
const ETF_SYMBOLS = ["BTC3L-USDT", "BTC3S-USDT", "ETH3L-USDT"];
type InstT = "SPOT" | "SWAP" | "FUTURES" | "OPTION" | "ETF";
const INST_TYPES: InstT[] = ["SPOT", "SWAP", "FUTURES", "OPTION", "ETF"];
const instType = ref<InstT>("SPOT");
const env = ref<"sim" | "live">("sim");

const form = ref({
  symbol: "BTC-USDT",
  side: "buy" as "buy" | "sell",
  ord_type: "market" as "market" | "limit",
  sz: "",
  px: "",
  lever: 10,
  strike: "",
  expiry: "",
  opt_type: "call" as "call" | "put",
  tp_px: "",
  sl_px: "",
});

const orders = ref<any[]>([]);
const positions = ref<any[]>([]);
const balances = ref<any[]>([]);
const trades = ref<any[]>([]);
const credentials = ref<any[]>([]);
const credId = ref<number | null>(null);
const lastPx = ref<Record<string, number>>({});
const confirmLive = ref(false);
const maxLever = ref(100);
let tradeWs: WebSocket | null = null;
let pxWs: WebSocket | null = null;

async function loadCredentials() {
  const r = await tradingApi.listCredentials(env.value);
  credentials.value = r.data;
  // 单套自动选中;多套保留当前选择或默认第一套
  if (credentials.value.length === 0) {
    credId.value = null;
  } else if (
    credId.value === null ||
    !credentials.value.some((c) => c.id === credId.value)
  ) {
    credId.value = credentials.value[0].id;
  }
}

async function refreshAll() {
  const [o, p, b, t] = await Promise.all([
    tradingApi.listOrders(env.value),
    tradingApi.listPositions(env.value),
    tradingApi.listBalances(env.value),
    tradingApi.listTrades(env.value),
  ]);
  orders.value = o.data;
  positions.value = p.data;
  balances.value = b.data;
  trades.value = t.data;
}

function extractError(e: any): string {
  const d = e?.response?.data;
  if (!d) return "";
  if (typeof d === "string") return d;
  if (d.detail) return String(d.detail);
  // DRF 字段错误:{ field: ["msg", ...] } → 取第一条
  const first = Object.values(d)[0];
  if (Array.isArray(first)) return String(first[0]);
  return typeof first === "string" ? first : JSON.stringify(d);
}

async function submit() {
  if (!form.value.sz) {
    toast.info(t("trade.enterSize"));
    return;
  }
  // 前端拦截:杠杆超出该品种官方上限(后端还有二次校验)
  if (
    (instType.value === "SWAP" || instType.value === "FUTURES") &&
    form.value.lever > maxLever.value
  ) {
    toast.error(`${t("trade.leverExceed")} (${maxLever.value}x)`);
    return;
  }
  if (env.value === "live") {
    confirmLive.value = true;
    return;
  }
  await doPlaceOrder();
}

async function doPlaceOrder() {
  confirmLive.value = false;
  const payload: OrderPayload = {
    env: env.value,
    inst_type: instType.value,
    symbol: form.value.symbol,
    side: form.value.side,
    ord_type: form.value.ord_type,
    sz: form.value.sz,
  };
  if (form.value.ord_type === "limit") payload.px = form.value.px;
  if (instType.value === "SWAP" || instType.value === "FUTURES") {
    payload.td_mode = "cross";
    payload.lever = form.value.lever;
  }
  if (instType.value === "OPTION") {
    payload.strike = form.value.strike;
    payload.expiry = form.value.expiry;
    payload.opt_type = form.value.opt_type;
  }
  if (showPositions.value) {
    if (form.value.tp_px) payload.tp_px = form.value.tp_px;
    if (form.value.sl_px) payload.sl_px = form.value.sl_px;
  }
  if (credId.value) payload.credential_id = credId.value;
  try {
    const r = await tradingApi.placeOrder(payload);
    toast.success(r.data.state === "filled" ? t("trade.filled") : t("trade.placed"));
    await refreshAll();
  } catch (e: any) {
    toast.error(extractError(e) || t("trade.orderFailed"));
  }
}

async function cancel(id: number) {
  await tradingApi.cancelOrder(id);
  await refreshAll();
}
async function closePos(id: number) {
  await tradingApi.closePosition(id);
  await refreshAll();
}

function upl(pos: any): number {
  const px = lastPx.value[pos.symbol];
  if (!px) return 0;
  const diff = pos.pos_side === "long" ? px - pos.avg_px : pos.avg_px - px;
  return diff * pos.qty;
}

function openTradeWs() {
  tradeWs?.close();
  const uid = auth.user?.id;
  if (!uid) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const token = localStorage.getItem("access") || "";
  tradeWs = new WebSocket(`${proto}://${location.host}/ws/trade/${uid}/${env.value}?token=${token}`);
  tradeWs.onmessage = (ev) => {
    try {
      const m = JSON.parse(ev.data);
      if (m.type && m.type !== "refresh") {
        // 风控事件:warning/liquidated/tp/sl → toast 提示
        const text = `${t("risk." + m.type)} · ${m.symbol}`;
        if (m.type === "tp") toast.success(text);
        else if (m.type === "warning") toast.info(text);
        else toast.error(text);
      }
    } catch {
      /* ignore */
    }
    refreshAll();
  };
}

function openPxWs() {
  pxWs?.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  // 复用行情 WS 拿最新价算浮盈(订阅当前下单标的)
  pxWs = new WebSocket(`${proto}://${location.host}/ws/market/${form.value.symbol}`);
  pxWs.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "ticker") lastPx.value[m.symbol] = m.last;
    else if (m.type === "candle") lastPx.value[m.symbol] = m.close;
  };
}

const spotBalances = computed(() =>
  balances.value.filter((b) => Number(b.total) !== 0)
);

const showLever = computed(() => instType.value === "SWAP" || instType.value === "FUTURES");
const showPositions = computed(() =>
  ["SWAP", "FUTURES", "OPTION"].includes(instType.value)
);

const credOptions = computed(() =>
  credentials.value.map((c) => ({ label: `${c.label} (${c.api_key_masked})`, value: c.id }))
);
const symbolOptions = computed(() => {
  if (instType.value === "ETF") return ETF_SYMBOLS.map((s) => ({ label: s, value: s }));
  const list = SYMBOLS_BY_TYPE.value[instType.value] ?? SYMBOLS.value;
  return list.map((s) => ({ label: s, value: s }));
});

const ordersPg = usePagination(orders, 10);
const positionsPg = usePagination(positions, 10);
const balancesPg = usePagination(spotBalances, 10);
const {
  page: ordersPage, pageSize: ordersSize, total: ordersTotal,
  totalPages: ordersPages, paged: ordersPaged,
} = ordersPg;
const {
  page: posPage, pageSize: posSize, total: posTotal,
  totalPages: posPages, paged: posPaged,
} = positionsPg;
const {
  page: balPage, pageSize: balSize, total: balTotal,
  totalPages: balPages, paged: balPaged,
} = balancesPg;

watch(instType, (t) => {
  // 切换品类时,symbol 换成对应品类的第一个,避免非法组合
  const list = t === "ETF" ? ETF_SYMBOLS : (SYMBOLS_BY_TYPE.value[t] ?? SYMBOLS.value);
  if (list.length && !list.includes(form.value.symbol)) form.value.symbol = list[0];
});

watch(env, () => {
  loadCredentials();
  refreshAll();
  openTradeWs();
});
watch(
  () => form.value.symbol,
  () => {
    openPxWs();
    loadMaxLever();
  }
);

async function loadMaxLever() {
  try {
    const { data } = await client.get(`/market/${form.value.symbol}/instrument`);
    maxLever.value = Math.max(1, Number(data.lever) || 1);
    if (form.value.lever > maxLever.value) form.value.lever = maxLever.value;
  } catch {
    maxLever.value = 100;
  }
}

onMounted(async () => {
  if (!auth.user) await auth.fetchMe();
  // 动态交易对列表(okx 模式返回真实全部,mock 返回内置);失败保留默认
  try {
    const r = await fetch("/api/market/symbols");
    const d = await r.json();
    if (d.by_type) {
      const bt: Record<string, string[]> = {};
      for (const k of Object.keys(d.by_type)) {
        bt[k] = d.by_type[k].map((x: any) => (typeof x === "string" ? x : x.instId));
      }
      SYMBOLS_BY_TYPE.value = bt;
    }
    if (Array.isArray(d.symbols) && d.symbols.length) SYMBOLS.value = d.symbols;
  } catch {
    /* 保留默认 */
  }
  await loadCredentials();
  await refreshAll();
  await loadMaxLever();
  openTradeWs();
  openPxWs();
});
onBeforeUnmount(() => {
  tradeWs?.close();
  pxWs?.close();
});
</script>

<template>
  <div class="trade-wrap">
    <!-- 顶部:品类页签 + 环境切换 -->
    <div class="glass bar">
      <div class="tabs">
        <button
          v-for="it in INST_TYPES"
          :key="it"
          class="tab"
          :class="{ active: instType === it }"
          @click="instType = it"
        >
          {{ $t("trade." + it.toLowerCase()) }}
        </button>
      </div>
      <div class="env">
        <span class="env-label">{{ $t("trade.env") }}:</span>
        <button
          class="tab"
          :class="{ active: env === 'sim' }"
          @click="env = 'sim'"
        >
          {{ $t("trade.sim") }}
        </button>
        <button
          class="tab live"
          :class="{ active: env === 'live' }"
          @click="env = 'live'"
        >
          {{ $t("trade.live") }}
        </button>
      </div>
    </div>

    <div class="grid">
      <!-- 下单面板 -->
      <div class="glass panel">
        <h3>{{ $t("trade.place") }}</h3>

        <label class="lbl">{{ $t("trade.credential") }}</label>
        <GlassSelect
          v-if="credentials.length"
          v-model="credId"
          :options="credOptions"
        />
        <p v-else class="nokey">
          {{ $t("trade.noKey") }}
          <router-link to="/settings/keys">{{ $t("nav.keys") }}</router-link>
        </p>

        <label class="lbl">{{ $t("trade.symbol") }}</label>
        <SearchSelect v-model="form.symbol" :options="symbolOptions" />

        <!-- 期权专属:方向 + 行权价 + 到期日 -->
        <template v-if="instType === 'OPTION'">
          <label class="lbl">{{ $t("trade.optType") }}</label>
          <div class="row">
            <button class="seg" :class="{ on: form.opt_type === 'call' }" @click="form.opt_type = 'call'">
              {{ $t("trade.call") }}
            </button>
            <button class="seg" :class="{ on: form.opt_type === 'put' }" @click="form.opt_type = 'put'">
              {{ $t("trade.put") }}
            </button>
          </div>
          <label class="lbl">{{ $t("trade.strike") }}</label>
          <GlassNumber
            :model-value="form.strike"
            @update:modelValue="(v: number) => (form.strike = String(v))"
          />
          <label class="lbl">{{ $t("trade.expiry") }}</label>
          <input class="input" v-model="form.expiry" type="date" />
        </template>

        <div class="row">
          <button
            class="seg buy"
            :class="{ on: form.side === 'buy' }"
            @click="form.side = 'buy'"
          >
            {{ $t("trade.buy") }}
          </button>
          <button
            class="seg sell"
            :class="{ on: form.side === 'sell' }"
            @click="form.side = 'sell'"
          >
            {{ $t("trade.sell") }}
          </button>
        </div>

        <div class="row">
          <button
            class="seg"
            :class="{ on: form.ord_type === 'market' }"
            @click="form.ord_type = 'market'"
          >
            {{ $t("trade.market") }}
          </button>
          <button
            class="seg"
            :class="{ on: form.ord_type === 'limit' }"
            @click="form.ord_type = 'limit'"
          >
            {{ $t("trade.limit") }}
          </button>
        </div>

        <template v-if="form.ord_type === 'limit'">
          <label class="lbl">{{ $t("trade.price") }}</label>
          <GlassNumber
            :model-value="form.px"
            @update:modelValue="(v: number) => (form.px = String(v))"
          />
        </template>

        <label class="lbl">{{ $t("trade.size") }}</label>
        <GlassNumber
          :model-value="form.sz"
          @update:modelValue="(v: number) => (form.sz = String(v))"
        />

        <template v-if="showLever">
          <label class="lbl">{{ $t("trade.lever") }}: {{ form.lever }}x</label>
          <GlassSlider v-model="form.lever" :min="1" :max="maxLever" />
        </template>

        <template v-if="showPositions">
          <label class="lbl">{{ $t("trade.tp") }}</label>
          <GlassNumber
            :model-value="form.tp_px"
            @update:modelValue="(v: number) => (form.tp_px = String(v))"
            :placeholder="$t('trade.optional')"
          />
          <label class="lbl">{{ $t("trade.sl") }}</label>
          <GlassNumber
            :model-value="form.sl_px"
            @update:modelValue="(v: number) => (form.sl_px = String(v))"
            :placeholder="$t('trade.optional')"
          />
        </template>

        <button class="btn submit" @click="submit">{{ $t("trade.submit") }}</button>
      </div>

      <!-- 右侧:持仓/余额 + 委托 + 成交 -->
      <div class="right">
        <div class="glass panel">
          <h3 v-if="showPositions">{{ $t("trade.positions") }}</h3>
          <h3 v-else>{{ $t("trade.balances") }}</h3>

          <table v-if="showPositions" class="tbl">
            <thead>
              <tr>
                <th>{{ $t("trade.symbol") }}</th>
                <th>{{ $t("trade.posSide") }}</th>
                <th>{{ $t("trade.qty") }}</th>
                <th>{{ $t("trade.avgPx") }}</th>
                <th>{{ $t("trade.upl") }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in posPaged" :key="p.id">
                <td>{{ p.symbol }}</td>
                <td>{{ p.pos_side === "long" ? $t("trade.long") : $t("trade.short") }}</td>
                <td>{{ p.qty }}</td>
                <td>{{ Number(p.avg_px).toFixed(2) }}</td>
                <td :class="upl(p) >= 0 ? 'up' : 'down'">{{ upl(p).toFixed(2) }}</td>
                <td>
                  <button class="btn btn-ghost sm" @click="closePos(p.id)">
                    {{ $t("trade.close") }}
                  </button>
                </td>
              </tr>
              <tr v-if="posTotal === 0">
                <td colspan="6" class="empty">{{ $t("trade.noPositions") }}</td>
              </tr>
            </tbody>
          </table>
          <Pagination
            v-if="showPositions && posTotal > 0"
            v-model:page="posPage"
            v-model:pageSize="posSize"
            :total="posTotal"
            :totalPages="posPages"
          />

          <table v-else class="tbl">
            <thead>
              <tr>
                <th>{{ $t("trade.ccy") }}</th>
                <th>{{ $t("trade.total") }}</th>
                <th>{{ $t("trade.available") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in balPaged" :key="b.id">
                <td>{{ b.ccy }}</td>
                <td>{{ Number(b.total).toFixed(4) }}</td>
                <td>{{ Number(b.available).toFixed(4) }}</td>
              </tr>
              <tr v-if="balTotal === 0">
                <td colspan="3" class="empty">{{ $t("trade.noBalance") }}</td>
              </tr>
            </tbody>
          </table>
          <Pagination
            v-if="!showPositions && balTotal > 0"
            v-model:page="balPage"
            v-model:pageSize="balSize"
            :total="balTotal"
            :totalPages="balPages"
          />
        </div>

        <div class="glass panel">
          <h3>{{ $t("trade.openOrders") }}</h3>
          <table class="tbl">
            <thead>
              <tr>
                <th>{{ $t("trade.symbol") }}</th>
                <th>{{ $t("trade.side") }}</th>
                <th>{{ $t("trade.type") }}</th>
                <th>{{ $t("trade.price") }}</th>
                <th>{{ $t("trade.size") }}</th>
                <th>{{ $t("trade.state") }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in ordersPaged" :key="o.id">
                <td>{{ o.symbol }}</td>
                <td :class="o.side === 'buy' ? 'up' : 'down'">
                  {{ o.side === "buy" ? $t("trade.buy") : $t("trade.sell") }}
                </td>
                <td>{{ ordTypeLabel(o.ord_type) }}</td>
                <td>{{ o.px ? Number(o.px).toFixed(2) : "—" }}</td>
                <td>{{ o.sz }}</td>
                <td>{{ orderStateLabel(o.state) }}</td>
                <td>
                  <button
                    v-if="o.state === 'live' || o.state === 'pending'"
                    class="btn btn-ghost sm"
                    @click="cancel(o.id)"
                  >
                    {{ $t("trade.cancel") }}
                  </button>
                </td>
              </tr>
              <tr v-if="ordersTotal === 0">
                <td colspan="7" class="empty">{{ $t("trade.noOrders") }}</td>
              </tr>
            </tbody>
          </table>
          <Pagination
            v-if="ordersTotal > 0"
            v-model:page="ordersPage"
            v-model:pageSize="ordersSize"
            :total="ordersTotal"
            :totalPages="ordersPages"
          />
        </div>
      </div>
    </div>

    <ConfirmDialog
      :open="confirmLive"
      :title="$t('trade.confirmLiveTitle')"
      :message="$t('trade.confirmLive')"
      danger
      @confirm="doPlaceOrder"
      @cancel="confirmLive = false"
    />
  </div>
</template>

<style scoped>
.trade-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  flex-wrap: wrap;
  gap: 12px;
}
.tabs,
.env {
  display: flex;
  gap: 6px;
  align-items: center;
}
.env-label {
  color: var(--fg-dim);
  font-size: 13px;
}
.tab {
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--fg-dim);
  border-radius: 10px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.tab.active {
  background: var(--glass-bg-strong);
  color: var(--fg);
  border-color: var(--accent);
}
.tab.live.active {
  border-color: #ff453a;
  color: #ff453a;
}
.grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.panel {
  padding: 18px;
}
.right {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
h3 {
  margin: 0 0 14px;
  font-size: 15px;
}
.lbl {
  display: block;
  font-size: 12px;
  color: var(--fg-dim);
  margin: 10px 0 4px;
}
.row {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.seg {
  flex: 1;
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--fg-dim);
  border-radius: 10px;
  padding: 8px;
  font-weight: 600;
  cursor: pointer;
}
.seg.on {
  background: var(--glass-bg-strong);
  color: var(--fg);
  border-color: var(--accent);
}
.seg.buy.on {
  border-color: #30d158;
  color: #30d158;
}
.seg.sell.on {
  border-color: #ff453a;
  color: #ff453a;
}
.submit {
  width: 100%;
  margin-top: 16px;
}
.nokey {
  font-size: 12px;
  color: #ff9f0a;
  margin: 4px 0 0;
}
.nokey a {
  color: var(--accent);
  margin-left: 4px;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.tbl th,
.tbl td {
  text-align: left;
  padding: 8px 6px;
  border-bottom: 1px solid var(--glass-border);
}
.tbl th {
  color: var(--fg-dim);
  font-weight: 600;
}
.up {
  color: #30d158;
}
.down {
  color: #ff453a;
}
.empty {
  color: var(--fg-dim);
  text-align: center;
  padding: 16px;
}
.sm {
  padding: 4px 10px;
  font-size: 12px;
}
</style>
