import { createI18n } from "vue-i18n";
import zhCN from "./zh-CN";
import enUS from "./en-US";

export type Locale = "zh-CN" | "en-US";

const saved = (localStorage.getItem("locale") as Locale) || "zh-CN";

const i18n = createI18n({
  legacy: false,
  locale: saved,
  fallbackLocale: "en-US",
  messages: { "zh-CN": zhCN, "en-US": enUS },
});

export function setLocale(locale: Locale) {
  i18n.global.locale.value = locale;
  localStorage.setItem("locale", locale);
  document.documentElement.lang = locale;
}

export default i18n;
