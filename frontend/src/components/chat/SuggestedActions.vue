<script setup lang="ts">
import type { Action } from '@/types/index'

defineProps<{
  actions: Action[]
}>()

const emit = defineEmits<{
  actionSelected: [action: Action]
}>()
</script>

<template>
  <div class="suggested-actions">
    <button
      v-for="action in actions"
      :key="action.label"
      class="action-btn"
      @click="emit('actionSelected', action)"
    >
      {{ action.label }}
    </button>
  </div>
</template>

<style scoped>
.suggested-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.action-btn {
  display: inline-block;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #0277BD;
  background: #fff;
  border: 1px solid #0277BD;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}
.action-btn:hover {
  background: #0277BD;
  color: #fff;
}
</style>
