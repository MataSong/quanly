import { defineStore } from "pinia";

export const useTerminal = defineStore("terminal", {
  state: () => ({
    symbol: "BTC-USDT",
    env: "sim" as "sim" | "live",
    instType: "SPOT",
    bar: "1m",
  }),
  actions: {
    setSymbol(s: string) {
      this.symbol = s;
    },
    setEnv(e: "sim" | "live") {
      this.env = e;
    },
    setInstType(t: string) {
      this.instType = t;
    },
    setBar(b: string) {
      this.bar = b;
    },
  },
});
