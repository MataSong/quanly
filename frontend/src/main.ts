import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";

import "@/styles/tokens.scss";
import "@/styles/base.scss";

import App from "./App.vue";

const app = createApp(App);
app.use(createPinia());
app.use(ElementPlus);
// Task 7 接 i18n: import { i18n } from "@/locales"; app.use(i18n)
// Task 8 接路由: import router from "@/router"; app.use(router)
app.mount("#app");
