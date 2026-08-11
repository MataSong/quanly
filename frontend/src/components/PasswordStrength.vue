<script setup lang="ts">
import { computed } from "vue";
import { checkPassword, passwordStrength } from "@/utils/password";

const props = defineProps<{ password: string }>();

const rules = computed(() => checkPassword(props.password));
const strength = computed(() => passwordStrength(props.password));

const strengthLabelKey = computed(() => {
  switch (strength.value) {
    case 0:
      return "password.strength.none";
    case 1:
      return "password.strength.weak";
    case 2:
      return "password.strength.medium";
    default:
      return "password.strength.strong";
  }
});
</script>

<template>
  <div v-if="password.length > 0" class="pw-strength">
    <div class="bars">
      <span
        v-for="i in 3"
        :key="i"
        class="bar"
        :class="{ active: i <= strength, [`lv${strength}`]: i <= strength }"
      />
      <span class="label">{{ $t(strengthLabelKey) }}</span>
    </div>
    <ul class="rules">
      <li v-for="r in rules" :key="r.key" :class="{ ok: r.passed }">
        <span class="mark">{{ r.passed ? "✓" : "✗" }}</span>
        {{ $t(r.key) }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.pw-strength {
  margin-top: -6px;
}
.bars {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.bar {
  flex: 1;
  height: 4px;
  border-radius: 2px;
  background: var(--glass-border);
  transition: background 0.2s ease;
}
.bar.lv1 {
  background: #ff453a;
}
.bar.lv2 {
  background: #ff9f0a;
}
.bar.lv3 {
  background: #30d158;
}
.label {
  font-size: 12px;
  color: var(--fg-dim);
  min-width: 32px;
}
.rules {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.rules li {
  font-size: 12px;
  color: var(--fg-dim);
}
.rules li.ok {
  color: #30d158;
}
.mark {
  display: inline-block;
  width: 14px;
}
</style>
