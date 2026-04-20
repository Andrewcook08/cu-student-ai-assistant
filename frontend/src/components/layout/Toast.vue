<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { useToastStore } from '@/stores/toastStore'

const toasts = useToastStore()
</script>

<template>
  <div class="toast-stack" role="region" aria-label="Notifications">
    <div
      v-for="t in toasts.toasts"
      :key="t.id"
      class="toast"
      :class="`toast--${t.level}`"
      :data-testid="`toast-${t.level}`"
      role="status"
      aria-live="polite"
    >
      <span class="toast__msg">{{ t.message }}</span>
      <button
        type="button"
        class="toast__close"
        aria-label="Dismiss notification"
        @click="toasts.dismiss(t.id)"
      >
        <X :size="14" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  top: 16px;
  right: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 2500;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
  max-width: 360px;
  padding: 10px 12px;
  border-radius: 4px;
  font-size: 13px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  pointer-events: auto;
  border: 1px solid transparent;
}

.toast--success {
  background: #f0fff4;
  color: #22543d;
  border-color: #9ae6b4;
}

.toast--info {
  background: #ebf8ff;
  color: #2c5282;
  border-color: #90cdf4;
}

.toast--error {
  background: #fff5f5;
  color: #742a2a;
  border-color: #fc8181;
}

.toast__msg {
  flex: 1;
}

.toast__close {
  background: none;
  border: none;
  color: inherit;
  opacity: 0.6;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 2px;
}

.toast__close:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.05);
}
</style>
