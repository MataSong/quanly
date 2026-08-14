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
app.use(createPinia());
app.use(ElementPlus);
app.use(i18n);
app.use(router);
app.mount("#app");
