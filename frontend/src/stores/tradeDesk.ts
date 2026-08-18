import { defineStore } from "pinia";
import { ref } from "vue";

/**
 * 交易台共享状态:让顶部选择栏、K线图、下单表单、监控区共享
 * 当前交易对/周期/凭证/产品类型,实现交易所式联动(切交易对图和下单同步)。
 */
export const useTradeDeskStore = defineStore("tradeDesk", () => {
  const symbol = ref("BTC-USDT");
  const bar = ref("1m");
  const credentialId = ref<number | null>(null);
  const instType = ref<"SPOT" | "SWAP">("SPOT");

  function setSymbol(s: string) {
    symbol.value = s;
  }
  function setBar(b: string) {
    bar.value = b;
  }
  function setCredential(id: number | null) {
    credentialId.value = id;
  }
  function setInstType(t: "SPOT" | "SWAP") {
    instType.value = t;
  }

  return {
    symbol,
    bar,
    credentialId,
    instType,
    setSymbol,
    setBar,
    setCredential,
    setInstType,
  };
});
