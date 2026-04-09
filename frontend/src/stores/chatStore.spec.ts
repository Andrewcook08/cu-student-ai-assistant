import { describe, it, expect } from 'vitest'
import { useChatStore } from './chatStore'

// test-setup.ts calls setActivePinia(createPinia()) before each test

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
})
