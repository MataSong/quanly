import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import { i18n } from "@/locales";
import router from "@/router";

import "element-plus/dist/index.css";
import "@/styles/tokens.scss";
import "@/styles/base.scss";
import "@/styles/element-overrides.scss";

import App from "./App.vue";

const app = createApp(App);

// 全局兜底:未被 ErrorBoundary 捕获的异常记录到 console,不静默吞掉。
app.config.errorHandler = (err, _instance, info) => {
  // eslint-disable-next-line no-console
  console.error("[vue errorHandler]", info, err);
};

app.use(createPinia());
app.use(ElementPlus);
app.use(i18n);
app.use(router);
app.mount("#app");
