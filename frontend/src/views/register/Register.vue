<template>
  <div class="login-page">
    <div class="login-blob login-blob-1"></div>
    <div class="login-blob login-blob-2"></div>

    <LocaleSwitcher class="login-locale" variant="glass" />

    <div class="glass-card">
      <div class="brand">
        <BrandLogo :size="40" variant="light" />
        <div class="brand-text">
          <div class="brand-title">{{ t("login.title") }}</div>
          <div class="brand-sub">{{ t("register.subtitle") }}</div>
        </div>
      </div>
      <h2>{{ t("register.title") }}</h2>
      <el-form :model="form" @submit.prevent="onSubmit">
        <div class="field" :class="{ 'has-value': form.username }"
             :style="{ '--label-w': usernameLabelW + 'px' }">
          <el-input v-model="form.username" autofocus autocomplete="username" />
          <label ref="usernameLabelEl">{{ t("register.username") }}</label>
        </div>
        <div class="field" :class="{ 'has-value': form.email }"
             :style="{ '--label-w': emailLabelW + 'px' }">
          <el-input v-model="form.email" type="email" autocomplete="email" />
          <label ref="emailLabelEl">{{ t("register.email") }}</label>
        </div>
        <div class="field" :class="{ 'has-value': form.password }"
             :style="{ '--label-w': passwordLabelW + 'px' }">
          <el-input v-model="form.password" type="password" show-password
                    autocomplete="new-password" />
          <label ref="passwordLabelEl">{{ t("register.password") }}</label>
        </div>
        <PasswordStrength :password="form.password" class="strength-widget" />
        <div class="field" :class="{ 'has-value': form.password2 }"
             :style="{ '--label-w': password2LabelW + 'px' }">
          <el-input v-model="form.password2" type="password" show-password
                    autocomplete="new-password" />
          <label ref="password2LabelEl">{{ t("register.confirmPassword") }}</label>
        </div>
        <el-button
          type="primary"
          native-type="submit"
          :loading="loading"
          class="submit-btn"
          @click="onSubmit"
        >
          {{ t("register.submit") }}
        </el-button>
        <div v-if="error" class="error">{{ error }}</div>
      </el-form>
      <div class="footer-link">
        <router-link to="/login">{{ t("register.goLogin") }}</router-link>
      </div>
    </div>
    <div class="login-footer">v0.2.0 · © 2026</div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted, nextTick, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useAuthStore } from "@/stores/auth";
import { checkRules } from "@/utils/password";
import LocaleSwitcher from "@/components/LocaleSwitcher.vue";
import BrandLogo from "@/components/BrandLogo.vue";
import PasswordStrength from "@/components/PasswordStrength.vue";

const { t, locale } = useI18n();
const form = reactive({ username: "", email: "", password: "", password2: "" });
const loading = ref(false);
const error = ref("");
const router = useRouter();
const auth = useAuthStore();

const usernameLabelEl = ref<HTMLElement | null>(null);
const emailLabelEl = ref<HTMLElement | null>(null);
const passwordLabelEl = ref<HTMLElement | null>(null);
const password2LabelEl = ref<HTMLElement | null>(null);
const usernameLabelW = ref(0);
const emailLabelW = ref(0);
const passwordLabelW = ref(0);
const password2LabelW = ref(0);

function measureLabels() {
  const scale = 12 / 14;
  function m(el: HTMLElement | null, target: { value: number }) {
    if (el) target.value = Math.ceil(el.offsetWidth * scale) + 8;
  }
  m(usernameLabelEl.value, usernameLabelW);
  m(emailLabelEl.value, emailLabelW);
  m(passwordLabelEl.value, passwordLabelW);
  m(password2LabelEl.value, password2LabelW);
}

onMounted(async () => {
  await nextTick();
  measureLabels();
});

watch(locale, async () => {
  await nextTick();
  measureLabels();
});

async function onSubmit() {
  error.value = "";
  if (!form.username) { error.value = t("register.usernameRequired"); return; }
  const rules = checkRules(form.password);
  if (!rules.valid) { error.value = t("register.weakPassword"); return; }
  if (form.password !== form.password2) { error.value = t("register.passwordMismatch"); return; }
  loading.value = true;
  try {
    await auth.register(form.username, form.password, form.email || undefined);
    router.replace("/dashboard");
  } catch (e: unknown) {
    const code = (e as any)?.response?.data?.code as string | undefined;
    const status = (e as any)?.response?.status as number | undefined;
    if (code === "user_exists") {
      error.value = t("register.userExists");
    } else if (code === "weak_password") {
      error.value = t("register.weakPassword");
    } else if (code === "bad_request" || status === 400) {
      error.value = t("register.badRequest");
    } else if (!(e as any)?.response) {
      error.value = t("register.networkError");
    } else {
      error.value = t("register.badRequest");
    }
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
  padding: 24px;
  overflow: hidden;
}

.login-blob {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  filter: blur(60px);
  pointer-events: none;
}
.login-blob-1 { width: 240px; height: 240px; top: 10%; left: 8%; }
.login-blob-2 { width: 320px; height: 320px; bottom: 8%; right: 6%; }

.login-locale {
  position: fixed;
  top: 24px;
  right: 24px;
  z-index: 10;
}

.glass-card {
  position: relative;
  z-index: 1;
  width: 400px;
  padding: 40px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.25);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  border-radius: 16px;
  color: rgba(255, 255, 255, 0.95);
  display: flex;
  flex-direction: column;
  gap: 20px;
}

@supports not (backdrop-filter: blur(1px)) {
  .glass-card {
    background: rgba(255, 255, 255, 0.85);
    color: #1f2937;
  }
}

.brand { display: flex; align-items: center; gap: 12px; }
.brand-title { font-size: 16px; font-weight: 600; }
.brand-sub   { font-size: 12px; opacity: 0.75; }

h2 { margin: 0; font-size: 20px; font-weight: 500; }

.field {
  position: relative;
  margin-bottom: 20px;
  --notch-x: 8px;
  --notch-w: 0px;
}
.field.has-value,
.field:focus-within {
  --notch-w: var(--label-w, 60px);
}
.field label {
  position: absolute;
  top: 50%;
  left: 12px;
  transform: translateY(-50%);
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
  pointer-events: none;
  transition: top 0.15s, font-size 0.15s, color 0.15s;
  background: transparent;
  padding: 0 4px;
  z-index: 2;
}
.field:focus-within label,
.field.has-value label {
  top: -8px;
  transform: translateY(0);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.95);
  background: transparent;
}

.field :deep(.el-input) { position: relative; }
.field :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.12);
  box-shadow: none;
  border-radius: 8px;
  height: 44px;
  position: relative;
}
.field :deep(.el-input__wrapper)::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 8px;
  pointer-events: none;
  padding: 1px;
  background: rgba(255, 255, 255, 0.3);
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
          mask-composite: exclude;
  clip-path: polygon(
    0 0,
    var(--notch-x) 0,
    var(--notch-x) 2px,
    calc(var(--notch-x) + var(--notch-w)) 2px,
    calc(var(--notch-x) + var(--notch-w)) 0,
    100% 0,
    100% 100%,
    0 100%
  );
  transition: clip-path 0.15s, background 0.15s;
}
.field :deep(.el-input__wrapper.is-focus)::after {
  background: rgba(255, 255, 255, 0.6);
}
.field :deep(.el-input__inner) { color: #fff; caret-color: #fff; }
.field :deep(.el-input__inner::placeholder) { color: transparent; }

.strength-widget {
  margin-top: -12px;
  margin-bottom: 8px;
}
.strength-widget :deep(.bar-label),
.strength-widget :deep(.rules li) {
  color: rgba(255, 255, 255, 0.65);
}
.strength-widget :deep(.rules li.ok)   { color: #86efac; }
.strength-widget :deep(.rules li.fail) { color: rgba(255, 255, 255, 0.45); }
.strength-widget :deep(.bar.empty) { background: rgba(255, 255, 255, 0.2); }

.submit-btn {
  width: 100%;
  height: 44px;
  background: rgba(255, 255, 255, 0.95);
  color: #4f46e5;
  border: none;
  font-weight: 600;
  border-radius: 8px;
  font-size: 15px;
  transition: transform 0.15s, box-shadow 0.15s;
}
.submit-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(255, 255, 255, 0.3);
}
.submit-btn:focus,
.submit-btn:active {
  background: rgba(255, 255, 255, 0.95);
  color: #4f46e5;
}

.error { color: #fecaca; font-size: 13px; margin-top: 8px; }

.footer-link { text-align: center; font-size: 13px; }
.footer-link a {
  color: rgba(255, 255, 255, 0.85);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.footer-link a:hover { color: #fff; }

.login-footer {
  position: relative;
  z-index: 1;
  margin-top: 24px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
}

@media (max-width: 768px) {
  .glass-card { width: 90%; padding: 24px; }
  .login-blob-1 { transform: scale(0.6); }
  .login-blob-2 { transform: scale(0.6); }
}
</style>
