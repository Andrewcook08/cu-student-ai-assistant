import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage } from '@/types/index'

const MAX_MESSAGES = 200

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isTyping = ref(false)
  const isConnected = ref(false)
  const isReconnecting = ref(false)
  const connectionError = ref<string | null>(null)
  const sessionId = ref<string | null>(null)

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
    if (messages.value.length > MAX_MESSAGES) {
      messages.value = messages.value.slice(-MAX_MESSAGES)
    }
  }

  function clearMessages() {
    messages.value = []
  }

  function setTyping(v: boolean) {
    isTyping.value = v
  }

  function setConnected(v: boolean) {
    isConnected.value = v
  }

  function setReconnecting(v: boolean) {
    isReconnecting.value = v
  }

  function setError(msg: string) {
    connectionError.value = msg
  }

  function clearError() {
    connectionError.value = null
  }

  function initSession(): string {
    if (!sessionId.value) {
      sessionId.value = crypto.randomUUID()
    }
    return sessionId.value!
  }

  return {
    messages,
    isTyping,
    isConnected,
    isReconnecting,
    connectionError,
    sessionId,
    addMessage,
    clearMessages,
    setTyping,
    setConnected,
    setReconnecting,
    setError,
    clearError,
    initSession,
  }
})
