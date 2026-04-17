import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useChatStore } from './chatStore'

// test-setup.ts calls setActivePinia(createPinia()) before each test

beforeEach(() => sessionStorage.clear())
afterEach(() => sessionStorage.clear())

describe('chatStore', () => {
  it('starts with empty messages', () => {
    const store = useChatStore()
    expect(store.messages).toEqual([])
  })

  it('starts with all flags false and no error', () => {
    const store = useChatStore()
    expect(store.isTyping).toBe(false)
    expect(store.isConnected).toBe(false)
    expect(store.isReconnecting).toBe(false)
    expect(store.connectionError).toBeNull()
  })

  it('addMessage appends a message to the list', () => {
    const store = useChatStore()
    store.addMessage({ role: 'user', content: 'hello' })
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0]).toEqual({ role: 'user', content: 'hello' })
  })

  it('addMessage preserves existing messages', () => {
    const store = useChatStore()
    store.addMessage({ role: 'user', content: 'first' })
    store.addMessage({ role: 'assistant', reply: 'second' })
    expect(store.messages).toHaveLength(2)
  })

  it('setTyping updates isTyping', () => {
    const store = useChatStore()
    store.setTyping(true)
    expect(store.isTyping).toBe(true)
    store.setTyping(false)
    expect(store.isTyping).toBe(false)
  })

  it('setConnected updates isConnected', () => {
    const store = useChatStore()
    store.setConnected(true)
    expect(store.isConnected).toBe(true)
  })

  it('setReconnecting updates isReconnecting', () => {
    const store = useChatStore()
    store.setReconnecting(true)
    expect(store.isReconnecting).toBe(true)
  })

  it('setError stores the message; clearError resets to null', () => {
    const store = useChatStore()
    store.setError('Authentication failed. Please log in again.')
    expect(store.connectionError).toBe('Authentication failed. Please log in again.')
    store.clearError()
    expect(store.connectionError).toBeNull()
  })

  it('initSession returns a stable UUID across calls', () => {
    const store = useChatStore()
    const first = store.initSession()
    const second = store.initSession()
    expect(first).toBe(second)
    expect(typeof first).toBe('string')
    expect(first.length).toBeGreaterThan(0)
  })

  it('caps messages at 200 — oldest dropped when exceeded', () => {
    const store = useChatStore()
    for (let i = 0; i < 205; i++) {
      store.addMessage({ role: 'user', content: `msg ${i}` })
    }
    expect(store.messages).toHaveLength(200)
    expect(store.messages[0].content).toBe('msg 5') // first 5 dropped
  })

  it('clearMessages empties the list', () => {
    const store = useChatStore()
    store.addMessage({ role: 'user', content: 'hello' })
    store.clearMessages()
    expect(store.messages).toHaveLength(0)
  })

  it('reset clears all per-user state', () => {
    const store = useChatStore()
    store.addMessage({ role: 'user', content: 'hi' })
    store.initSession()
    store.setTyping(true)
    store.setStreaming(true)
    store.setToolStatus('working')
    store.setError('boom')
    store.setReconnecting(true)

    store.reset()

    expect(store.messages).toEqual([])
    expect(store.sessionId).toBeNull()
    expect(store.isTyping).toBe(false)
    expect(store.isStreaming).toBe(false)
    expect(store.toolStatus).toBeNull()
    expect(store.connectionError).toBeNull()
    expect(store.isReconnecting).toBe(false)
  })

  it('initSession(userId) persists the UUID to sessionStorage', () => {
    const store = useChatStore()
    const uuid = store.initSession(42)
    expect(sessionStorage.getItem('chat-session-42')).toBe(uuid)
  })

  it('initSession(userId) restores the persisted UUID after reset', () => {
    const store = useChatStore()
    const first = store.initSession(42)
    store.reset()
    const second = store.initSession(42)
    expect(second).toBe(first)
  })

  it('initSession(userId) isolates UUIDs across different users', () => {
    const store = useChatStore()
    const aliceUuid = store.initSession(1)
    store.reset()
    const bobUuid = store.initSession(2)
    expect(bobUuid).not.toBe(aliceUuid)
    expect(sessionStorage.getItem('chat-session-1')).toBe(aliceUuid)
    expect(sessionStorage.getItem('chat-session-2')).toBe(bobUuid)
  })

  it('initSession() without userId does not write to sessionStorage', () => {
    const store = useChatStore()
    store.initSession()
    expect(sessionStorage.length).toBe(0)
  })
})
