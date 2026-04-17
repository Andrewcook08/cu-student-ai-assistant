import { onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chatStore'
import { useAuthStore } from '@/stores/authStore'
import type { WsClientMessage, WsServerMessage } from '@/types/index'

const WS_OPEN = 1 // WebSocket.OPEN — avoids dependency on global being set correctly

// In dev, VITE_WS_URL is unset and we fall back to the chat-service port.
// In the prod build we derive the WS URL from the browser origin so the
// connection goes back through the frontend's nginx, which proxies /ws/*
// to chat-service. This keeps everything same-origin and avoids CORS
// handling on the WebSocket upgrade.
const WS_BASE_URL = (() => {
  const explicit = import.meta.env.VITE_WS_URL
  if (explicit) return explicit
  if (import.meta.env.PROD && typeof window !== 'undefined') {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}`
  }
  return 'ws://localhost:8001'
})()
const NO_RECONNECT_CODES = new Set([4001, 4002, 1008, 1009])
const MAX_RECONNECT_DELAY = 30_000

const CLOSE_ERROR_MESSAGES: Record<number, string> = {
  4001: 'Authentication failed. Please log in again.',
  4002: 'Session expired. Please log in again.',
  1008: 'Connection closed: policy violation.',
  1009: 'Connection closed: message too large.',
}

export function useChat() {
  const store = useChatStore()
  let ws: WebSocket | null = null
  let reconnectAttempt = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    if (ws && ws.readyState <= WS_OPEN) return  // already connected or connecting
    const sid = store.initSession()
    const authStore = useAuthStore()
    const token = authStore.token ?? ''
    ws = new WebSocket(`${WS_BASE_URL}/ws/chat/${sid}?token=${token}`)

    ws.onopen = () => {
      store.setConnected(true)
      store.setReconnecting(false)
      store.clearError()
      reconnectAttempt = 0
    }

    // Message routing — matches WsServerMessage contract in types/index.ts.
    // Backend (CHAT-002+) must send type: 'error' for errors and type: 'progress'
    // for progress updates. The stub (CHAT-001) is an echo server only.
    ws.onmessage = (event: MessageEvent) => {
      let data: WsServerMessage
      try {
        data = JSON.parse(event.data as string)
      } catch {
        return // malformed frame — skip, don't crash
      }

      if (data.type === 'token') {
        store.setStreaming(true)
        store.setToolStatus(null)
        store.appendToken(data.token ?? '')
      } else if (data.type === 'typing') {
        store.setTyping(true)
      } else if (data.type === 'progress') {
        store.setToolStatus(data.message ?? 'Working...')
      } else if (data.type === 'chat_response') {
        store.setTyping(false)
        store.setStreaming(false)
        store.setToolStatus(null)
        // If we already streamed tokens into the last message, update it
        // with the final reply + structured data instead of adding a duplicate.
        const last = store.messages[store.messages.length - 1]
        if (last && last.role === 'assistant' && last.reply) {
          last.structured_data = data.structured_data
          last.suggested_actions = data.suggested_actions
        } else {
          store.addMessage({
            role: 'assistant',
            reply: data.reply,
            structured_data: data.structured_data,
            suggested_actions: data.suggested_actions,
          })
        }
      } else if (data.type === 'error') {
        store.setTyping(false)
        store.addMessage({
          role: 'system',
          content: data.error ?? 'Something went wrong.',
        })
      }
    }

    ws.onerror = () => {
      // onclose fires after onerror — reconnection is handled there
    }

    ws.onclose = (event: CloseEvent) => {
      store.setConnected(false)
      store.setTyping(false)

      if (NO_RECONNECT_CODES.has(event.code)) {
        const errMsg = CLOSE_ERROR_MESSAGES[event.code] ?? 'Connection closed.'
        store.setError(errMsg)
        store.addMessage({ role: 'system', content: errMsg })
        return
      }

      store.setReconnecting(true)
      const delay = Math.min(1_000 * 2 ** reconnectAttempt, MAX_RECONNECT_DELAY)
      reconnectAttempt++
      reconnectTimer = setTimeout(() => connect(), delay)
    }
  }

  function send(message: string, context?: WsClientMessage['context']) {
    if (!ws || ws.readyState !== WS_OPEN) return
    if (!message.trim()) return  // match backend's validation — no blank bubbles
    store.addMessage({ role: 'user', content: message })
    const payload: WsClientMessage = {
      type: 'chat_message',
      message,
      session_id: store.sessionId ?? undefined,
      context,
    }
    ws.send(JSON.stringify(payload))
  }

  function disconnect() {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    ws?.close()
    ws = null
    reconnectAttempt = 0
  }

  onUnmounted(disconnect)

  return { connect, send, disconnect }
}
