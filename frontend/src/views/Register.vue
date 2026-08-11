<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { setLocale, type Locale } from "@/i18n";
import { useAuth } from "@/stores/auth";
import { isPasswordValid } from "@/utils/password";
import GlassField from "@/components/GlassField.vue";
import PasswordStrength from "@/components/PasswordStrength.vue";

const router = useRouter();
const auth = useAuth();
const { locale } = useI18n();

const username = ref("");
const email = ref("");
const password = ref("");
const password2 = ref("");
const error = ref("");

const passwordOk = computed(() => isPasswordValid(password.value));
const matchOk = computed(
  () => password2.value.length > 0 && password.value === password2.value
);
const canSubmit = computed(
  () => username.value.length > 0 && passwordOk.value && matchOk.value
);

async function submit() {
  error.value = "";
  if (!canSubmit.value) return;
  try {
    await auth.register(username.value, email.value, password.value);
    router.push("/login");
  } catch {
    error.value = "register.failed";
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
      <h1>{{ $t("register.title") }}</h1>

      <GlassField v-model="username" :label="$t('login.username')" autofocus />
      <GlassField v-model="email" :label="$t('register.email')" />
      <GlassField v-model="password" :label="$t('login.password')" type="password" />
      <PasswordStrength :password="password" />
      <GlassField
        v-model="password2"
        :label="$t('register.confirmPassword')"
        type="password"
        @enter="submit"
      />
      <p v-if="password2.length > 0 && !matchOk" class="err">
        {{ $t("register.mismatch") }}
      </p>

      <p v-if="error" class="err">{{ $t(error) }}</p>
      <button class="btn" :disabled="!canSubmit" @click="submit">
        {{ $t("register.submit") }}
      </button>
      <router-link to="/login" class="link">{{ $t("register.toLogin") }}</router-link>
    </div>
  </div>
</template>

<style scoped>
.auth-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px 0;
}
.card {
  position: relative;
  width: 360px;
  padding: 34px;
  display: flex;
  flex-direction: column;
  gap: 18px;
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
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
