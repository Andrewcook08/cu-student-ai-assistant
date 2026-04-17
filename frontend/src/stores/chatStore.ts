import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage } from '@/types/index'

const MAX_MESSAGES = 200

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isTyping = ref(false)
  const isStreaming = ref(false)
  const toolStatus = ref<string | null>(null)
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

  function setToolStatus(msg: string | null) {
    toolStatus.value = msg
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

  // Persist (and restore) the session UUID in sessionStorage, keyed by userId.
  // Same user logging back in within the tab's lifetime and Redis's 2h TTL
  // keeps the LLM's conversation context intact. Different userId means a
  // different key, so no cross-user leakage is possible.
  function initSession(userId: number | null = null): string {
    if (sessionId.value) return sessionId.value
    if (userId !== null) {
      const stored = sessionStorage.getItem(`chat-session-${userId}`)
      if (stored) {
        sessionId.value = stored
        return stored
      }
    }
    const fresh = crypto.randomUUID()
    sessionId.value = fresh
    if (userId !== null) {
      sessionStorage.setItem(`chat-session-${userId}`, fresh)
    }
    return fresh
  }

  function reset() {
    messages.value = []
    sessionId.value = null
    isTyping.value = false
    isStreaming.value = false
    toolStatus.value = null
    connectionError.value = null
    isReconnecting.value = false
  }

  return {
    messages,
    isTyping,
    isStreaming,
    toolStatus,
    isConnected,
    isReconnecting,
    connectionError,
    sessionId,
    addMessage,
    appendToken,
    clearMessages,
    setTyping,
    setStreaming,
    setToolStatus,
    setConnected,
    setReconnecting,
    setError,
    clearError,
    initSession,
    reset,
  }
})
