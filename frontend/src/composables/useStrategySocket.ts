/**
 * useStrategySocket — WebSocket composable for real-time strategy log streaming.
 *
 * Connects to /ws/strategy/<runId>/?token=<access_token>
 * Token is taken from the auth store (SimpleJWT access token).
 * Calls onLog(entry) whenever a log message arrives.
 * Reconnects automatically with exponential back-off on unexpected close.
 * Code 4001 = auth failure → no retry.
 */
import { ref, onUnmounted } from "vue";
import { useAuthStore } from "@/stores/auth";
import type { StrategyLog } from "@/api/strategy";

export type LogHandler = (entry: StrategyLog) => void;

const WS_BASE = (() => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}`;
})();

export function useStrategySocket(runId: number, onLog: LogHandler) {
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

    const url = `${WS_BASE}/ws/strategy/${runId}/?token=${encodeURIComponent(token)}`;
    ws = new WebSocket(url);

    ws.onopen = () => {
      connected.value = true;
      error.value = null;
      retryDelay = 2000;
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data as string);
        // Backend StrategyLogConsumer sends {type, level, message, ts}
        if (msg.level !== undefined && msg.message !== undefined) {
          onLog({ level: msg.level, message: msg.message, ts: msg.ts ?? "" });
        }
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
