import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage } from '@/types/index'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const sessionId = ref<string>(crypto.randomUUID())
  const isConnected = ref(false)
  const isTyping = ref(false)
  const isReconnecting = ref(false)

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
  }

  function clearMessages() {
    messages.value = []
  }

  function newSession() {
    sessionId.value = crypto.randomUUID()
    messages.value = []
  }

  return {
    messages,
    sessionId,
    isConnected,
    isTyping,
    isReconnecting,
    addMessage,
    clearMessages,
    newSession,
  }
})
