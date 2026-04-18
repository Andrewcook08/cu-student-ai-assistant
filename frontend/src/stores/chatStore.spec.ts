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

  it('addMessage persists transcript to sessionStorage once initSession(userId) is called', () => {
    const store = useChatStore()
    store.initSession(42)
    store.addMessage({ role: 'user', content: 'hi' })
    store.addMessage({ role: 'assistant', reply: 'hello there' })

    const raw = sessionStorage.getItem('chat-messages-42')
    expect(raw).not.toBeNull()
    expect(JSON.parse(raw as string)).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', reply: 'hello there' },
    ])
  })

  it('appendToken persists streaming updates for later restore', () => {
    const store = useChatStore()
    store.initSession(42)
    store.appendToken('Hel')
    store.appendToken('lo')

    const raw = sessionStorage.getItem('chat-messages-42')
    expect(JSON.parse(raw as string)).toEqual([
      { role: 'assistant', reply: 'Hello' },
    ])
  })

  it('applyFinalAssistant persists structured_data on an existing streamed bubble', () => {
    const store = useChatStore()
    store.initSession(42)
    store.appendToken('Here are courses')
    store.applyFinalAssistant({
      reply: 'Here are courses',
      structured_data: [{ code: 'CSCI 1300', title: 'Intro CS', credits: '3' }],
      suggested_actions: [{ type: 'search', label: 'more', payload: {} }],
    })

    const msgs = JSON.parse(sessionStorage.getItem('chat-messages-42') as string)
    expect(msgs).toHaveLength(1)
    expect(msgs[0].structured_data).toHaveLength(1)
    expect(msgs[0].suggested_actions).toHaveLength(1)
  })

  it('applyFinalAssistant adds a new bubble when no streaming happened', () => {
    const store = useChatStore()
    store.initSession(42)
    store.applyFinalAssistant({
      reply: 'hi',
      structured_data: undefined,
      suggested_actions: undefined,
    })

    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].role).toBe('assistant')
    expect(store.messages[0].reply).toBe('hi')
  })

  it('reset clears in-memory messages but leaves sessionStorage transcript intact', () => {
    const store = useChatStore()
    store.initSession(42)
    store.addMessage({ role: 'user', content: 'hello' })
    store.reset()

    expect(store.messages).toEqual([])
    expect(sessionStorage.getItem('chat-messages-42')).not.toBeNull()
  })

  it('after reset + initSession(same userId), messages hydrate back into the panel', () => {
    const store = useChatStore()
    store.initSession(42)
    store.addMessage({ role: 'user', content: 'hello' })
    store.addMessage({ role: 'assistant', reply: 'hi there' })
    store.reset()

    store.initSession(42)

    expect(store.messages).toEqual([
      { role: 'user', content: 'hello' },
      { role: 'assistant', reply: 'hi there' },
    ])
  })

  it('initSession(userId) does not restore another users transcript', () => {
    const store = useChatStore()
    store.initSession(1)
    store.addMessage({ role: 'user', content: 'alice secret' })
    store.reset()

    store.initSession(2)

    expect(store.messages).toEqual([])
  })

  it('addMessage does not write to sessionStorage after reset (no active userId)', () => {
    const store = useChatStore()
    store.initSession(42)
    store.reset()
    store.addMessage({ role: 'user', content: 'post-reset' })

    // chat-messages-42 still holds whatever was there before reset — here
    // there was nothing persisted before this specific sequence, so it
    // remains null. Key guarantee: we did NOT write post-reset content.
    const raw = sessionStorage.getItem('chat-messages-42')
    const parsed = raw ? JSON.parse(raw) : null
    expect(parsed).not.toEqual([{ role: 'user', content: 'post-reset' }])
  })

  it('clearMessages wipes the persisted transcript', () => {
    const store = useChatStore()
    store.initSession(42)
    store.addMessage({ role: 'user', content: 'hello' })
    store.clearMessages()

    expect(sessionStorage.getItem('chat-messages-42')).toBe('[]')
  })

  it('initSession(userId) with malformed storage falls back to empty transcript', () => {
    sessionStorage.setItem('chat-session-42', '11111111-1111-4111-8111-111111111111')
    sessionStorage.setItem('chat-messages-42', 'not-valid-json{')
    const store = useChatStore()
    store.initSession(42)
    expect(store.messages).toEqual([])
  })

  it('newSession rotates the UUID, clears messages, and wipes persisted transcript', () => {
    const store = useChatStore()
    const originalUuid = store.initSession(42)
    store.addMessage({ role: 'user', content: 'hello' })
    expect(sessionStorage.getItem('chat-messages-42')).not.toBeNull()

    const freshUuid = store.newSession(42)

    expect(freshUuid).not.toBe(originalUuid)
    expect(store.sessionId).toBe(freshUuid)
    expect(store.messages).toEqual([])
    expect(sessionStorage.getItem('chat-session-42')).toBe(freshUuid)
    expect(sessionStorage.getItem('chat-messages-42')).toBeNull()
  })

  it('after newSession, subsequent addMessage persists under the new UUID only', () => {
    const store = useChatStore()
    store.initSession(42)
    store.newSession(42)
    store.addMessage({ role: 'user', content: 'first on fresh session' })

    const raw = sessionStorage.getItem('chat-messages-42')
    expect(JSON.parse(raw as string)).toEqual([
      { role: 'user', content: 'first on fresh session' },
    ])
  })
})
