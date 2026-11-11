import { createApp } from "vue";

import App from "@/App.vue";
import { initAuth } from "@/auth";

import "@/styles.css";

initAuth();
createApp(App).mount("#app");
