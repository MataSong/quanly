<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    label: string;
    type?: "text" | "password";
    autocomplete?: string;
    autofocus?: boolean;
  }>(),
  { type: "text", autocomplete: "off", autofocus: false }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "enter"): void;
}>();

const { locale } = useI18n();

const revealed = ref(false);
const labelEl = ref<HTMLElement | null>(null);
const labelW = ref(0);

const isPassword = computed(() => props.type === "password");
const inputType = computed(() =>
  isPassword.value && !revealed.value ? "password" : "text"
);
const hasValue = computed(() => props.modelValue.length > 0);

// 测量标签宽度,给边框缺口用
function measureLabel() {
  if (labelEl.value) {
    const scale = 12 / 14; // 上浮后字号从 14 缩到 12
    labelW.value = Math.ceil(labelEl.value.offsetWidth * scale) + 8;
  }
}

onMounted(async () => {
  await nextTick();
  measureLabel();
});

// 语言切换后标签宽度变化,重新测量
watch(locale, async () => {
  await nextTick();
  measureLabel();
});

function onInput(e: Event) {
  emit("update:modelValue", (e.target as HTMLInputElement).value);
}
</script>

<template>
  <div
    class="field"
    :class="{ 'has-value': hasValue }"
    :style="{ '--label-w': labelW + 'px' }"
  >
    <input
      class="field-input"
      :class="{ 'has-reveal': isPassword }"
      :type="inputType"
      :value="modelValue"
      :autocomplete="autocomplete"
      :autofocus="autofocus"
      @input="onInput"
      @keyup.enter="emit('enter')"
    />
    <label ref="labelEl">{{ label }}</label>
    <button
      v-if="isPassword"
      type="button"
      class="reveal"
      :aria-pressed="revealed"
      :title="revealed ? $t('common.hidePwd') : $t('common.showPwd')"
      @click="revealed = !revealed"
    >
      <svg
        v-if="!revealed"
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
      <svg
        v-else
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c6.5 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
        <path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3.5 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
        <path d="M14.12 14.12A3 3 0 1 1 9.88 9.88" />
        <line x1="2" y1="2" x2="22" y2="22" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.field {
  position: relative;
  --notch-x: 10px;
  --notch-w: 0px;
}
.field.has-value,
.field:focus-within {
  --notch-w: var(--label-w, 60px);
}

.field-input {
  width: 100%;
  height: 46px;
  padding: 0 14px;
  background: var(--glass-bg-strong);
  border: none;
  border-radius: 10px;
  color: var(--fg);
  font-size: 14px;
  outline: none;
  position: relative;
}
.field-input::placeholder {
  color: transparent;
}
.field-input.has-reveal {
  padding-right: 42px;
}

/* 边框(带缺口)用伪元素画,聚焦时缺口张开让标签嵌入 */
.field::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 10px;
  pointer-events: none;
  padding: 1px;
  background: var(--glass-border);
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
  transition: clip-path 0.15s ease, background 0.15s ease;
}
.field:focus-within::after {
  background: var(--accent);
}

.field label {
  position: absolute;
  top: 50%;
  left: 14px;
  transform: translateY(-50%);
  font-size: 14px;
  color: var(--fg-dim);
  pointer-events: none;
  padding: 0 4px;
  z-index: 2;
  transition: top 0.15s ease, font-size 0.15s ease, color 0.15s ease;
}
.field:focus-within label,
.field.has-value label {
  top: -8px;
  transform: translateY(0);
  font-size: 12px;
  color: var(--accent);
}

.reveal {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 6px;
  color: var(--fg-dim);
  opacity: 0.8;
  z-index: 2;
  transition: color 0.15s ease, opacity 0.15s ease;
}
.reveal:hover {
  opacity: 1;
  color: var(--fg);
}
</style>
