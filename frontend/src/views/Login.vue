<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { setLocale, type Locale } from "@/i18n";
import { useAuth } from "@/stores/auth";
import GlassField from "@/components/GlassField.vue";

const router = useRouter();
const auth = useAuth();
const { locale } = useI18n();

const username = ref("");
const password = ref("");
const error = ref("");

async function submit() {
  error.value = "";
  try {
    await auth.login(username.value, password.value);
    router.push("/dashboard");
  } catch {
    error.value = "login.failed";
  }
}

function toggleLocale() {
  const next: Locale = locale.value === "zh-CN" ? "en-US" : "zh-CN";
  setLocale(next);
}
</script>

<template>
  <div class="auth-wrap">
    <div class="card glass-strong">
      <button class="lang-toggle btn btn-ghost" @click="toggleLocale">
        {{ locale === "zh-CN" ? "EN" : "中" }}
      </button>
      <h1>{{ $t("login.title") }}</h1>
      <GlassField v-model="username" :label="$t('login.username')" autofocus />
      <GlassField
        v-model="password"
        :label="$t('login.password')"
        type="password"
        @enter="submit"
      />
      <p v-if="error" class="err">{{ $t(error) }}</p>
      <button class="btn" @click="submit">{{ $t("login.submit") }}</button>
      <router-link to="/register" class="link">{{ $t("login.toRegister") }}</router-link>
    </div>
  </div>
</template>

<style scoped>
.auth-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}
.card {
  position: relative;
  width: 360px;
  padding: 34px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.lang-toggle {
  position: absolute;
  top: 16px;
  right: 16px;
  padding: 4px 10px;
}
h1 {
  margin: 0 0 4px;
  font-size: 24px;
}
.err {
  color: #ff453a;
  font-size: 13px;
  margin: 0;
}
.link {
  color: var(--accent);
  font-size: 13px;
  text-decoration: none;
  text-align: center;
}
</style>
