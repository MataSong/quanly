<template>
  <svg class="brand-logo" :width="size" :height="size"
       viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg"
       role="img" aria-label="quanly logo">
    <defs>
      <linearGradient :id="gradId" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" :stop-color="from" />
        <stop offset="100%" :stop-color="to" />
      </linearGradient>
    </defs>

    <!-- Hexagon background -->
    <path
      d="M20 2.5 L34.5 10.75 V29.25 L20 37.5 L5.5 29.25 V10.75 Z"
      :fill="`url(#${gradId})`" />

    <!-- Candlestick / chart icon representing quantitative trading -->
    <g :stroke="strokeColor" stroke-width="1.5" stroke-linecap="round"
       stroke-linejoin="round" fill="none" opacity="0.95">
      <!-- Rising candle left -->
      <rect x="12" y="15" width="4" height="8" rx="0.5" :stroke="strokeColor" />
      <line x1="14" y1="13" x2="14" y2="15" />
      <line x1="14" y1="23" x2="14" y2="26" />
      <!-- Falling candle right -->
      <rect x="24" y="18" width="4" height="6" rx="0.5" :stroke="strokeColor" />
      <line x1="26" y1="15" x2="26" y2="18" />
      <line x1="26" y1="24" x2="26" y2="27" />
      <!-- Trend line -->
      <path d="M11 27 L20 19 L29 14" />
    </g>
  </svg>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{
  size?: number | string;
  variant?: "light" | "dark";
}>(), { size: 32, variant: "light" });

const from = computed(() =>
  props.variant === "dark" ? "rgba(255,255,255,0.18)" : "#635bff"
);
const to = computed(() =>
  props.variant === "dark" ? "rgba(255,255,255,0.04)" : "#00d4ff"
);
const strokeColor = computed(() => "#ffffff");

const gradId = `ql-bg-${Math.random().toString(36).slice(2, 8)}`;
</script>

<style scoped>
.brand-logo {
  display: block;
  filter: drop-shadow(0 2px 6px rgba(99, 91, 255, 0.30));
}
</style>
