import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import { i18n } from "@/locales";
import router from "@/router";

import "@/styles/tokens.scss";
import "@/styles/base.scss";

import App from "./App.vue";

const app = createApp(App);
app.use(createPinia());
app.use(ElementPlus);
app.use(i18n);
app.use(router);
app.mount("#app");
