import { onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chatStore'
import type { WsClientMessage, WsServerMessage } from '@/types/index'

const WS_OPEN = 1 // WebSocket.OPEN — avoids dependency on global being set correctly
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
    const sid = store.initSession()
    const token = localStorage.getItem('token') ?? ''
    ws = new WebSocket(`ws://localhost:8001/ws/chat/${sid}?token=${token}`)

    ws.onopen = () => {
      store.setConnected(true)
      store.setReconnecting(false)
      store.clearError()
      reconnectAttempt = 0
    }

    ws.onmessage = (event: MessageEvent) => {
      const data: WsServerMessage = JSON.parse(event.data as string)

      if (data.type === 'typing') {
        store.setTyping(true)
      } else if (data.type === 'progress') {
        store.addMessage({
          role: 'system',
          content: data.message ?? 'Still working on your response...',
        })
      } else if (data.type === 'chat_response') {
        store.setTyping(false)
        store.addMessage({
          role: 'assistant',
          reply: data.reply,
          structured_data: data.structured_data,
          suggested_actions: data.suggested_actions,
        })
      } else if (data.type === 'error') {
        store.setTyping(false)
        store.addMessage({
          role: 'system',
          content: data.error ?? 'Something went wrong.',
        })
      }
    }

    ws.onclose = (event: CloseEvent) => {
      store.setConnected(false)

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
  }

  onUnmounted(disconnect)

  return { connect, send, disconnect }
}
