import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useChat } from './useChat'
import { useChatStore } from '@/stores/chatStore'

// ---------------------------------------------------------------------------
// MockWebSocket — replaces global WebSocket in jsdom
// ---------------------------------------------------------------------------
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState = MockWebSocket.CONNECTING
  sent: string[] = []
  url: string

  onopen: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: ((e: CloseEvent) => void) | null = null

  constructor(url: string) {
    this.url = url
  }

  send(data: string) { this.sent.push(data) }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  simulateClose(code = 1000) {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code, reason: '', wasClean: code === 1000 } as CloseEvent)
  }
}

let instance: MockWebSocket

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.stubGlobal('WebSocket', class extends MockWebSocket {
    constructor(url: string) {
      super(url)
      instance = this
    }
  })
  localStorage.setItem('token', 'test-jwt')
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  vi.clearAllTimers()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('useChat — connect', () => {
  it('creates a WebSocket with the correct URL structure', () => {
    const { connect } = useChat()
    connect()
    expect(instance.url).toMatch(/^ws:\/\/localhost:8001\/ws\/chat\/[^?]+\?token=test-jwt$/)
  })

  it('uses the token from localStorage', () => {
    localStorage.setItem('token', 'secret-token')
    const { connect } = useChat()
    connect()
    expect(instance.url).toContain('?token=secret-token')
  })

  it('uses empty string token when localStorage has none', () => {
    localStorage.removeItem('token')
    const { connect } = useChat()
    connect()
    expect(instance.url).toContain('?token=')
  })

  it('uses a stable session ID (same UUID across reconnects)', () => {
    vi.useFakeTimers()
    let wsCount = 0
    vi.stubGlobal('WebSocket', class extends MockWebSocket {
      constructor(url: string) {
        super(url)
        wsCount++
        instance = this
      }
    })

    const { connect } = useChat()
    connect()
    const firstUrl = instance.url
    instance.simulateOpen()
    instance.simulateClose(1006)
    vi.advanceTimersByTime(1100)

    const secondUrl = instance.url
    const sessionFrom = (url: string) => url.split('/ws/chat/')[1].split('?')[0]
    expect(sessionFrom(firstUrl)).toBe(sessionFrom(secondUrl))
    vi.useRealTimers()
  })
})

describe('useChat — onopen', () => {
  it('sets isConnected, clears reconnecting, clears error', () => {
    const { connect } = useChat()
    const store = useChatStore()
    store.setReconnecting(true)
    store.setError('old error')

    connect()
    instance.simulateOpen()

    expect(store.isConnected).toBe(true)
    expect(store.isReconnecting).toBe(false)
    expect(store.connectionError).toBeNull()
  })
})

describe('useChat — onmessage', () => {
  it('typing → sets isTyping to true', () => {
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    instance.simulateMessage({ type: 'typing' })

    expect(store.isTyping).toBe(true)
  })

  it('chat_response → adds assistant message, clears isTyping', () => {
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()
    store.setTyping(true)

    instance.simulateMessage({
      type: 'chat_response',
      reply: 'Here are some courses.',
      structured_data: [{ code: 'CSCI 1300', title: 'Intro CS', credits: '3' }],
      suggested_actions: [{ type: 'search', label: 'Show more', payload: {} }],
    })

    expect(store.isTyping).toBe(false)
    expect(store.messages).toHaveLength(1)
    const msg = store.messages[0]
    expect(msg.role).toBe('assistant')
    expect(msg.reply).toBe('Here are some courses.')
    expect(msg.structured_data).toHaveLength(1)
    expect(msg.suggested_actions).toHaveLength(1)
  })

  it('error → adds system message with error text, clears isTyping', () => {
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()
    store.setTyping(true)

    instance.simulateMessage({ type: 'error', error: 'LLM timed out.' })

    expect(store.isTyping).toBe(false)
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('system')
    expect(store.messages[0].content).toBe('LLM timed out.')
  })

  it('error with no error field → falls back to generic message', () => {
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    instance.simulateMessage({ type: 'error' })

    expect(store.messages[0].content).toBe('Something went wrong.')
  })

  it('progress → adds system message with progress text', () => {
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    instance.simulateMessage({ type: 'progress', message: 'Still working on your response...' })

    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('system')
    expect(store.messages[0].content).toBe('Still working on your response...')
  })

  it('progress with no message → falls back to default text', () => {
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    instance.simulateMessage({ type: 'progress' })

    expect(store.messages[0].content).toBe('Still working on your response...')
  })
})

describe('useChat — onclose (security)', () => {
  it('code 4001 → sets auth error message, does NOT reconnect', () => {
    vi.useFakeTimers()
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    instance.simulateClose(4001)

    expect(store.connectionError).toBe('Authentication failed. Please log in again.')
    expect(store.messages.some(m => m.content?.includes('Authentication failed'))).toBe(true)
    const urlBefore = instance.url
    vi.advanceTimersByTime(35_000)
    expect(instance.url).toBe(urlBefore) // same instance, no reconnect
    vi.useRealTimers()
  })

  it('code 4002 → sets session-expired error, does NOT reconnect', () => {
    vi.useFakeTimers()
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    instance.simulateClose(4002)

    expect(store.connectionError).toBe('Session expired. Please log in again.')
    vi.advanceTimersByTime(35_000)
    expect(store.isReconnecting).toBe(false)
    vi.useRealTimers()
  })

  it('code 1008 → sets policy-violation error, does NOT reconnect', () => {
    vi.useFakeTimers()
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    instance.simulateClose(1008)

    expect(store.connectionError).toBe('Connection closed: policy violation.')
    expect(store.messages.some(m => m.content?.includes('policy violation'))).toBe(true)
    vi.advanceTimersByTime(35_000)
    expect(store.isReconnecting).toBe(false)
    vi.useRealTimers()
  })

  it('code 1009 → sets message-too-large error, does NOT reconnect', () => {
    vi.useFakeTimers()
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    instance.simulateClose(1009)

    expect(store.connectionError).toBe('Connection closed: message too large.')
    expect(store.messages.some(m => m.content?.includes('message too large'))).toBe(true)
    vi.advanceTimersByTime(35_000)
    expect(store.isReconnecting).toBe(false)
    vi.useRealTimers()
  })

  it('code 1006 (abnormal) → sets isReconnecting, schedules reconnect', () => {
    vi.useFakeTimers()
    let wsCount = 0
    vi.stubGlobal('WebSocket', class extends MockWebSocket {
      constructor(url: string) {
        super(url)
        wsCount++
        instance = this
      }
    })

    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()
    instance.simulateClose(1006)

    expect(store.isReconnecting).toBe(true)
    expect(wsCount).toBe(1) // not yet reconnected

    vi.advanceTimersByTime(1100) // first backoff = 1s
    expect(wsCount).toBe(2)
    vi.useRealTimers()
  })

  it('backoff delay doubles each attempt (1s → 2s → 4s)', () => {
    vi.useFakeTimers()
    let wsCount = 0
    vi.stubGlobal('WebSocket', class extends MockWebSocket {
      constructor(url: string) {
        super(url)
        wsCount++
        instance = this
      }
    })

    const { connect } = useChat()
    connect() // wsCount = 1
    instance.simulateOpen()

    // Attempt 0: reconnectAttempt=0 → delay = 1s
    instance.simulateClose(1006)
    expect(wsCount).toBe(1) // no reconnect yet
    vi.advanceTimersByTime(999)
    expect(wsCount).toBe(1) // still waiting
    vi.advanceTimersByTime(1) // 1000ms elapsed → reconnect fires
    expect(wsCount).toBe(2)
    // Do NOT simulateOpen — reconnectAttempt stays at 1

    // Attempt 1: reconnectAttempt=1 → delay = 2s
    instance.simulateClose(1006)
    vi.advanceTimersByTime(1999)
    expect(wsCount).toBe(2) // still waiting
    vi.advanceTimersByTime(1) // 2000ms elapsed → reconnect fires
    expect(wsCount).toBe(3)
    // Do NOT simulateOpen — reconnectAttempt stays at 2

    // Attempt 2: reconnectAttempt=2 → delay = 4s
    instance.simulateClose(1006)
    vi.advanceTimersByTime(3999)
    expect(wsCount).toBe(3) // still waiting
    vi.advanceTimersByTime(1) // 4000ms elapsed → reconnect fires
    expect(wsCount).toBe(4)

    vi.useRealTimers()
  })
})

describe('useChat — onclose (general)', () => {
  it('clears isTyping on any close', () => {
    const { connect } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()
    store.setTyping(true)

    instance.simulateClose(1000)

    expect(store.isTyping).toBe(false)
  })
})

describe('useChat — send', () => {
  it('adds user message to store and sends JSON to WebSocket', () => {
    const { connect, send } = useChat()
    const store = useChatStore()
    connect()
    instance.simulateOpen()

    send('What CS courses can I take?')

    expect(store.messages).toHaveLength(1)
    expect(store.messages[0]).toEqual({ role: 'user', content: 'What CS courses can I take?' })
    expect(instance.sent).toHaveLength(1)
    const payload = JSON.parse(instance.sent[0])
    expect(payload.type).toBe('chat_message')
    expect(payload.message).toBe('What CS courses can I take?')
  })

  it('includes context when provided', () => {
    const { connect, send } = useChat()
    connect()
    instance.simulateOpen()

    send('hello', { selected_program: 'CS BS', completed_courses: ['CSCI 1300'] })

    const payload = JSON.parse(instance.sent[0])
    expect(payload.context.selected_program).toBe('CS BS')
    expect(payload.context.completed_courses).toEqual(['CSCI 1300'])
  })

  it('does nothing if WebSocket is not OPEN', () => {
    const { connect, send } = useChat()
    const store = useChatStore()
    connect()
    // Do NOT simulateOpen — readyState stays CONNECTING

    send('hello')

    expect(store.messages).toHaveLength(0)
    expect(instance.sent).toHaveLength(0)
  })
})
