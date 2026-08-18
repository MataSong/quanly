/**
 * useMarketSocket — WebSocket composable for real-time market data.
 *
 * Connects to /ws/market/<symbol>/?token=<access_token>&bar=<bar>
 * Token is taken from the auth store (SimpleJWT access token).
 * bar 告知后端为该连接订阅对应周期的 candle 频道。
 * 回调分离:onCandle(整根 K 线更新) / onTicker(最新成交价,驱动末根 close 秒级跳)。
 * Reconnects automatically with exponential back-off on unexpected close.
 */
import { ref, onUnmounted } from "vue";
import { useAuthStore } from "@/stores/auth";
import type { Candle } from "@/api/market";

export interface Ticker {
  last: string;
}

export interface MarketSocketHandlers {
  onCandle?: (candle: Candle) => void;
  onTicker?: (ticker: Ticker) => void;
}

const WS_BASE = (() => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}`;
})();

export function useMarketSocket(
  symbol: string,
  bar: string,
  handlers: MarketSocketHandlers,
) {
  const auth = useAuthStore();
  const connected = ref(false);
  const error = ref<string | null>(null);

  let ws: WebSocket | null = null;
  let retryDelay = 2000;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let destroyed = false;

  function connect() {
    if (destroyed) return;
    const token = auth.access;
    if (!token) {
      error.value = "no_token";
      return;
    }

    const url =
      `${WS_BASE}/ws/market/${symbol}/?token=${encodeURIComponent(token)}` +
      `&bar=${encodeURIComponent(bar)}`;
    ws = new WebSocket(url);

    ws.onopen = () => {
      connected.value = true;
      error.value = null;
      retryDelay = 2000;
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data as string);
        if (msg.type !== "market_update") return;
        if (msg.candle) handlers.onCandle?.(msg.candle as Candle);
        if (msg.ticker) handlers.onTicker?.(msg.ticker as Ticker);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      error.value = "ws_error";
    };

    ws.onclose = (evt) => {
      connected.value = false;
      ws = null;
      // 4001 = auth failure, do not retry
      if (evt.code === 4001) {
        error.value = "auth_failed";
        return;
      }
      if (!destroyed) {
        retryTimer = setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 30000);
          connect();
        }, retryDelay);
      }
    };
  }

  function disconnect() {
    destroyed = true;
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
  }

  onUnmounted(disconnect);

  connect();

  return { connected, error, disconnect };
}
