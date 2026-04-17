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

  // The userId to use when persisting messages to sessionStorage. Set by
  // initSession(userId) and cleared by reset(). Null means "don't persist" —
  // mirrors the pre-auth state and lets tests run without writing storage.
  let persistUserId: number | null = null

  function persistMessages() {
    if (persistUserId === null) return
    sessionStorage.setItem(
      `chat-messages-${persistUserId}`,
      JSON.stringify(messages.value),
    )
  }

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
    if (messages.value.length > MAX_MESSAGES) {
      messages.value = messages.value.slice(-MAX_MESSAGES)
    }
    persistMessages()
  }

  function appendToken(token: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.reply = (last.reply ?? '') + token
    } else {
      messages.value.push({ role: 'assistant', reply: token })
    }
    persistMessages()
  }

  // Called by useChat when chat_response arrives and we already streamed
  // tokens into the last message — we attach the structured data/actions
  // to the existing assistant bubble instead of duplicating it. Needs its
  // own entry point so the in-place mutation gets persisted.
  function applyFinalAssistant(data: {
    reply?: string
    structured_data?: ChatMessage['structured_data']
    suggested_actions?: ChatMessage['suggested_actions']
  }) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.reply) {
      last.structured_data = data.structured_data
      last.suggested_actions = data.suggested_actions
      persistMessages()
    } else {
      addMessage({
        role: 'assistant',
        reply: data.reply,
        structured_data: data.structured_data,
        suggested_actions: data.suggested_actions,
      })
    }
  }

  function clearMessages() {
    messages.value = []
    persistMessages()
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

  // Persist (and restore) the session UUID + message history in sessionStorage,
  // keyed by userId. Same user logging back in within the tab's lifetime and
  // Redis's 2h TTL keeps both the LLM's conversation context (server-side,
  // keyed by session_id) and the visible chat transcript (client-side) intact.
  // Different userId means different keys, so no cross-user leakage.
  function initSession(userId: number | null = null): string {
    if (userId !== null) persistUserId = userId
    if (sessionId.value) return sessionId.value
    if (userId !== null) {
      const storedUuid = sessionStorage.getItem(`chat-session-${userId}`)
      if (storedUuid) {
        sessionId.value = storedUuid
        const storedMsgs = sessionStorage.getItem(`chat-messages-${userId}`)
        if (storedMsgs) {
          try {
            const parsed = JSON.parse(storedMsgs)
            if (Array.isArray(parsed)) messages.value = parsed
          } catch {
            // malformed — ignore, start with empty transcript
          }
        }
        return storedUuid
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
    // Stop persisting until the next initSession(userId). The sessionStorage
    // entries for chat-session-<userId> and chat-messages-<userId> survive
    // so a same-user re-login can restore both UUID and transcript.
    persistUserId = null
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
    applyFinalAssistant,
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
