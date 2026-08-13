import { createI18n } from "vue-i18n";
import zh from "./zh-CN";
import en from "./en-US";

export const i18n = createI18n({
  legacy: false,
  locale: "zh-CN",
  fallbackLocale: "zh-CN",
  messages: { "zh-CN": zh, "en-US": en },
  missingWarn: import.meta.env.DEV,
  fallbackWarn: import.meta.env.DEV,
});

export function t(key: string, named?: Record<string, unknown>): string {
  return i18n.global.t(key, named ?? {}) as string;
}
