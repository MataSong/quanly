import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";

import "@/styles/tokens.scss";
import "@/styles/base.scss";

import App from "./App.vue";

// TODO(Task 7): import router from "@/router" and app.use(router)
// TODO(Task 8): import { i18n } from "@/locales" and app.use(i18n)

const app = createApp(App);
app.use(createPinia());
// app.use(router);   // Task 7
// app.use(i18n);     // Task 8
app.use(ElementPlus);
app.mount("#app");
