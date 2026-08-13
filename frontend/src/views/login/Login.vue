<template>
  <div class="login-page">
    <div class="login-bg" />

    <div class="login-card">
      <div class="login-header">
        <BrandLogo :size="48" variant="light" />
        <h1 class="login-title">{{ t("login.title") }}</h1>
        <p class="login-sub">{{ t("login.subtitle") }}</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @submit.prevent="onSubmit"
      >
        <el-form-item :label="t('login.username')" prop="username">
          <el-input
            v-model="form.username"
            :placeholder="t('login.usernamePlaceholder')"
            autocomplete="username"
            autofocus
          />
        </el-form-item>
        <el-form-item :label="t('login.password')" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="t('login.passwordPlaceholder')"
            autocomplete="current-password"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-alert
          v-if="errorMsg"
          :title="errorMsg"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom: 12px;"
        />
        <el-button
          type="primary"
          native-type="submit"
          :loading="loading"
          style="width: 100%;"
          @click="onSubmit"
        >
          {{ t("login.submit") }}
        </el-button>
      </el-form>

      <div class="login-locale">
        <LocaleSwitcher variant="glass" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import type { FormInstance, FormRules } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import BrandLogo from "@/components/BrandLogo.vue";
import LocaleSwitcher from "@/components/LocaleSwitcher.vue";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const formRef = ref<FormInstance>();
const loading = ref(false);
const errorMsg = ref("");

const form = reactive({ username: "", password: "" });

const rules: FormRules = {
  username: [{ required: true, message: t("login.usernameRequired"), trigger: "blur" }],
  password: [{ required: true, message: t("login.passwordRequired"), trigger: "blur" }],
};

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  loading.value = true;
  errorMsg.value = "";
  try {
    await auth.login(form.username, form.password);
    const next = (route.query.next as string) || "/dashboard";
    router.replace(next);
  } catch (e: unknown) {
    const status = (e as any)?.response?.status;
    if (status === 401 || status === 400) {
      errorMsg.value = t("login.invalid");
    } else if (status === 403) {
      errorMsg.value = t("login.inactive");
    } else {
      errorMsg.value = t("login.networkError");
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
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.login-bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--brand-dark) 0%, #1a365d 60%, #0d1b2a 100%);
  z-index: 0;
}

.login-card {
  position: relative;
  z-index: 1;
  background: #fff;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  padding: var(--space-8) var(--space-7);
  width: 100%;
  max-width: 420px;
}

.login-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-7);
  text-align: center;
}

.login-title {
  margin: 0;
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--gray-800);
}

.login-sub {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--gray-500);
}

.login-locale {
  display: flex;
  justify-content: center;
  margin-top: var(--space-6);
}

/* Dark locale switcher on white card: override glass variant colors */
:deep(.locale-switcher.glass) {
  background: rgba(10, 37, 64, 0.06);
  backdrop-filter: none;
  border-color: var(--gray-200);
  color: var(--gray-600);
}
:deep(.locale-switcher.glass button) { color: var(--gray-600); }
:deep(.locale-switcher.glass button.active) { color: var(--brand-primary); }
</style>
