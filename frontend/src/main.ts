import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import { i18n } from "@/locales";

import "@/styles/tokens.scss";
import "@/styles/base.scss";

import App from "./App.vue";

const app = createApp(App);
app.use(createPinia());
app.use(ElementPlus);
app.use(i18n);
// Task 8 接路由: import router from "@/router"; app.use(router)
app.mount("#app");
