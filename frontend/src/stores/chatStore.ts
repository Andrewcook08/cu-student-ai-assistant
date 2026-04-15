import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage } from '@/types/index'

const MAX_MESSAGES = 200

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isTyping = ref(false)
  const isStreaming = ref(false)
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

  function appendToken(token: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.reply = (last.reply ?? '') + token
    } else {
      messages.value.push({ role: 'assistant', reply: token })
    }
  }

  function clearMessages() {
    messages.value = []
  }

  function setTyping(v: boolean) {
    isTyping.value = v
  }

  function setStreaming(v: boolean) {
    isStreaming.value = v
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
    isStreaming,
    isConnected,
    isReconnecting,
    connectionError,
    sessionId,
    addMessage,
    appendToken,
    clearMessages,
    setTyping,
    setStreaming,
    setConnected,
    setReconnecting,
    setError,
    clearError,
    initSession,
  }
})
