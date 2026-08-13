import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { i18n } from "@/locales";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import en from "element-plus/es/locale/lang/en";

export type AppLocale = "zh-CN" | "en-US";
const STORAGE_KEY = "quanly:locale";

function detectInitial(): AppLocale {
  const saved = localStorage.getItem(STORAGE_KEY) as AppLocale | null;
  if (saved === "zh-CN" || saved === "en-US") return saved;
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

export const useLocaleStore = defineStore("locale", () => {
  const current = ref<AppLocale>(detectInitial());

  const elementLocale = computed(() =>
    current.value === "zh-CN" ? zhCn : en
  );

  function setLocale(loc: AppLocale) {
    if (loc === current.value) return;
    current.value = loc;
    i18n.global.locale.value = loc;
    localStorage.setItem(STORAGE_KEY, loc);
    document.documentElement.lang = loc;
  }

  i18n.global.locale.value = current.value;
  document.documentElement.lang = current.value;

  return { current, elementLocale, setLocale };
});
