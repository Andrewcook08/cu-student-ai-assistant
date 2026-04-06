import { onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chatStore'
import type { WsClientMessage, WsServerMessage } from '@/types/index'

const WS_BASE = '/ws/chat'
const MAX_RECONNECT_DELAY_MS = 30_000

// Module-level state: only one WebSocket instance exists for the lifetime of the app.
// useChat() may be called from multiple components but they all share this socket.
let ws: WebSocket | null = null
let reconnectAttempt = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let destroyed = false

export function useChat() {
  const store = useChatStore()

  function getToken(): string {
    return localStorage.getItem('token') ?? ''
  }

  function connect() {
    if (destroyed) return

    const url = `${WS_BASE}/${store.sessionId}?token=${encodeURIComponent(getToken())}`
    ws = new WebSocket(url)

    ws.onopen = () => {
      store.isConnected = true
      store.isReconnecting = false
      reconnectAttempt = 0
    }

    ws.onmessage = (event: MessageEvent) => {
      let data: WsServerMessage
      try {
        data = JSON.parse(event.data as string) as WsServerMessage
      } catch {
        return
      }

      switch (data.type) {
        case 'typing':
          store.isTyping = true
          break
        case 'progress':
          // Show progress message (still typing, but keep indicator)
          store.isTyping = true
          if (data.message) {
            store.addMessage({ role: 'system', content: data.message })
          }
          break
        case 'chat_response':
          store.isTyping = false
          store.addMessage({
            role: 'assistant',
            reply: data.reply,
            structured_data: data.structured_data,
            suggested_actions: data.suggested_actions,
          })
          break
        case 'error':
          store.isTyping = false
          store.addMessage({
            role: 'system',
            content: data.error ?? 'Something went wrong. Please try again.',
          })
          break
      }
    }

    ws.onerror = () => {
      // onerror is always followed by onclose — let onclose handle reconnect
    }

    ws.onclose = () => {
      store.isConnected = false
      store.isTyping = false

      if (!destroyed) {
        scheduleReconnect()
      }
    }
  }

  function scheduleReconnect() {
    store.isReconnecting = true
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), MAX_RECONNECT_DELAY_MS)
    reconnectAttempt++
    reconnectTimer = setTimeout(() => {
      if (!destroyed) connect()
    }, delay)
  }

  function send(message: string, context?: WsClientMessage['context']) {
    // Always record the user's message so it isn't lost on disconnect
    store.addMessage({ role: 'user', content: message })
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      store.addMessage({
        role: 'system',
        content: 'Not connected. Please wait for reconnection.',
      })
      return
    }
    const payload: WsClientMessage = {
      type: 'chat_message',
      message,
      session_id: store.sessionId,
      context,
    }
    ws.send(JSON.stringify(payload))
  }

  function disconnect() {
    destroyed = true
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    ws?.close()
    ws = null
  }

  onUnmounted(disconnect)

  return { connect, send, disconnect }
}
