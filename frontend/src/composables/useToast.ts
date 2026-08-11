import { ref } from "vue";

export interface Toast {
  id: number;
  text: string;
  type: "info" | "error" | "success";
}

const toasts = ref<Toast[]>([]);
let seq = 0;

export function useToast() {
  function push(text: string, type: Toast["type"] = "info", ms = 3000) {
    const id = ++seq;
    toasts.value.push({ id, text, type });
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id);
    }, ms);
  }
  return {
    toasts,
    info: (t: string) => push(t, "info"),
    error: (t: string) => push(t, "error", 5000),
    success: (t: string) => push(t, "success"),
  };
}
