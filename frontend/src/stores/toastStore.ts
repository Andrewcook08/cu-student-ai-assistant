import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastLevel = 'success' | 'info' | 'error'

export interface Toast {
  id: number
  level: ToastLevel
  message: string
}

const DEFAULT_DURATION_MS = 3000

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])
  let nextId = 1

  function push(input: { level: ToastLevel; message: string; durationMs?: number }): number {
    const id = nextId++
    toasts.value.push({ id, level: input.level, message: input.message })
    const duration = input.durationMs ?? DEFAULT_DURATION_MS
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration)
    }
    return id
  }

  function dismiss(id: number): void {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  function clear(): void {
    toasts.value = []
  }

  return { toasts, push, dismiss, clear }
})
