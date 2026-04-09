import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage } from '@/types/index'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isTyping = ref(false)
  const isConnected = ref(false)
  const isReconnecting = ref(false)
  const connectionError = ref<string | null>(null)
  const sessionId = ref<string | null>(null)

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
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

  function setError(msg: string | null) {
    connectionError.value = msg
  }

  function clearError() {
    connectionError.value = null
  }

  function initSession() {
    if (!sessionId.value) {
      sessionId.value = crypto.randomUUID()
    }
    return sessionId.value
  }

  return {
    messages,
    isTyping,
    isConnected,
    isReconnecting,
    connectionError,
    sessionId,
    addMessage,
    setTyping,
    setConnected,
    setReconnecting,
    setError,
    clearError,
    initSession,
  }
})
