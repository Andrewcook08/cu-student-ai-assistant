<script setup lang="ts">
import { ref, computed } from 'vue'
import { Send } from 'lucide-vue-next'

const props = defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  send: [message: string]
}>()

const input = ref('')
const MAX_CHARS = 2000

const charCount = computed(() => input.value.length)
const isOverLimit = computed(() => charCount.value > MAX_CHARS)
const canSend = computed(() => input.value.trim().length > 0 && !props.disabled && !isOverLimit.value)

function handleSend() {
  if (!canSend.value) return
  emit('send', input.value.trim())
  input.value = ''
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}
</script>

<template>
  <div class="chat-input-bar">
    <div class="chat-input__field">
      <textarea
        v-model="input"
        class="chat-input__textarea"
        aria-label="Message input"
        maxlength="2000"
        :placeholder="disabled ? 'AI is thinking...' : 'Ask me anything about courses...'"
        :disabled="disabled"
        rows="1"
        @keydown="handleKeydown"
      />
      <span
        v-if="charCount > 0"
        class="chat-input__counter"
        :class="{ 'chat-input__counter--over': isOverLimit }"
      >
        {{ charCount }}/{{ MAX_CHARS }}
      </span>
    </div>
    <button
      class="chat-input__send"
      :disabled="!canSend"
      :title="disabled ? 'AI is thinking...' : 'Send message'"
      @click="handleSend"
    >
      <Send :size="16" />
    </button>
  </div>
</template>

<style scoped>
.chat-input-bar {
  display: flex;
  align-items: start;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid #ddd;
  background: #fff;
  flex-shrink: 0;
}
.chat-input__field {
  flex: 1;
  position: relative;
}
.chat-input__textarea {
  width: 100%;
  box-sizing: border-box;
  resize: none;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 7px 10px;
  font-size: 13px;
  font-family: inherit;
  line-height: 1.4;
  color: #333;
  background: #fff;
  max-height: 100px;
  overflow-y: auto;
  transition: border-color 0.15s;
}
.chat-input__textarea:focus {
  outline: none;
  border-color: #CFB87C;
  box-shadow: 0 0 0 2px rgba(207, 184, 124, 0.25);
}
.chat-input__textarea:disabled {
  background: #f5f5f5;
  color: #999;
  cursor: not-allowed;
}
.chat-input__send {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  background: #CFB87C;
  color: #000;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}
.chat-input__send:hover:not(:disabled) {
  background: #c4a94f;
}
.chat-input__send:disabled {
  background: #e0e0e0;
  color: #999;
  cursor: not-allowed;
}
.chat-input__counter {
  position: absolute;
  top: 10px;
  right: 8px;
  font-size: 10px;
  color: #bbb;
  pointer-events: none;
}
.chat-input__counter--over {
  color: #c62828;
  font-weight: 600;
}
</style>
