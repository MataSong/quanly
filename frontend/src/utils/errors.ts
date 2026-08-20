import { t, i18n } from "@/locales";

/**
 * Extract a human-readable error message from an Axios error response.
 * ns: i18n namespace for code-keyed messages (e.g. "admin", "common").
 */
export function formatApiError(e: unknown, ns: string, fallback?: string): string {
  const body = (e as any)?.response?.data;
  const code = body?.code;
  if (typeof code === "string") {
    const key = `${ns}.${code}`;
    if (i18n.global.te(key)) return t(key);
  }
  // detail 是后端(DRF)主要报错字段;OKX/Order 等第三方异常原文也在此,先能显示。
  return body?.detail || body?.message || (e as any)?.message || fallback || t("common.error");
}
