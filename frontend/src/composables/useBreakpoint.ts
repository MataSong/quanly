import { onBeforeUnmount, ref } from "vue";

/**
 * 响应式断点判断。返回的 isMobile 会随窗口宽度变化自动更新。
 * 断点(768px)与 src/styles/mixins.scss 的 $bp-mobile 保持一致。
 *
 * 用法:
 *   const { isMobile } = useBreakpoint();
 *   // 模板/computed 里用 isMobile.value
 */
const MOBILE_QUERY = "(max-width: 768px)";

export function useBreakpoint() {
  const mql = window.matchMedia(MOBILE_QUERY);
  const isMobile = ref(mql.matches);

  const onChange = (e: MediaQueryListEvent) => {
    isMobile.value = e.matches;
  };

  // addEventListener 在现代浏览器可用;旧 Safari 用 addListener 兜底
  if (typeof mql.addEventListener === "function") {
    mql.addEventListener("change", onChange);
  } else {
    mql.addListener(onChange);
  }

  onBeforeUnmount(() => {
    if (typeof mql.removeEventListener === "function") {
      mql.removeEventListener("change", onChange);
    } else {
      mql.removeListener(onChange);
    }
  });

  return { isMobile };
}
