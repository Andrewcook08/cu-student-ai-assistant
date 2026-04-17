import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useAuthStore } from './authStore'
import { useChatStore } from './chatStore'

// test-setup.ts calls setActivePinia(createPinia()) before each test

beforeEach(() => sessionStorage.clear())
afterEach(() => sessionStorage.clear())

describe('authStore', () => {
  it('starts unauthenticated with null token and userId', () => {
    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(false)
    expect(store.userName).toBe('')
    expect(store.token).toBeNull()
    expect(store.userId).toBeNull()
  })

  it('setAuth updates state and persists to sessionStorage', () => {
    const store = useAuthStore()
    store.setAuth('jwt-abc', 7, 'Alice')
    expect(store.isAuthenticated).toBe(true)
    expect(store.userName).toBe('Alice')
    expect(store.token).toBe('jwt-abc')
    expect(store.userId).toBe(7)
    expect(sessionStorage.getItem('token')).toBe('jwt-abc')
    expect(sessionStorage.getItem('userId')).toBe('7')
    expect(sessionStorage.getItem('userName')).toBe('Alice')
  })

  it('logout clears state and removes from sessionStorage', () => {
    const store = useAuthStore()
    store.setAuth('jwt-abc', 7, 'Alice')
    store.logout()
    expect(store.isAuthenticated).toBe(false)
    expect(store.userName).toBe('')
    expect(store.token).toBeNull()
    expect(store.userId).toBeNull()
    expect(sessionStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('userId')).toBeNull()
    expect(sessionStorage.getItem('userName')).toBeNull()
  })

  it('logout wipes the chat panel so the next user starts fresh', () => {
    const auth = useAuthStore()
    const chat = useChatStore()
    auth.setAuth('jwt-abc', 7, 'Alice')
    chat.addMessage({ role: 'user', content: 'secret' })
    chat.initSession(7)

    auth.logout()

    expect(chat.messages).toEqual([])
    expect(chat.sessionId).toBeNull()
  })

  // header.payload.sig — payload = {"sub":1,"exp":9999999999} (year 2286, never expires in tests)
  const validJwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6OTk5OTk5OTk5OX0.sig'
  // payload = {"sub":1,"exp":1} (epoch + 1 second — always expired)
  const expiredJwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6MX0.sig'

  it('initFromStorage restores auth state from sessionStorage for a valid token', () => {
    sessionStorage.setItem('token', validJwt)
    sessionStorage.setItem('userId', '99')
    sessionStorage.setItem('userName', 'Bob')
    const store = useAuthStore()
    store.initFromStorage()
    expect(store.isAuthenticated).toBe(true)
    expect(store.token).toBe(validJwt)
    expect(store.userId).toBe(99)
    expect(store.userName).toBe('Bob')
  })

  it('initFromStorage does nothing when sessionStorage is empty', () => {
    const store = useAuthStore()
    store.initFromStorage()
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
  })

  it('initFromStorage calls logout for an expired token', () => {
    sessionStorage.setItem('token', expiredJwt)
    sessionStorage.setItem('userId', '99')
    sessionStorage.setItem('userName', 'Bob')
    const store = useAuthStore()
    store.initFromStorage()
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
    expect(sessionStorage.getItem('token')).toBeNull()
  })

  it('initFromStorage calls logout for a malformed token', () => {
    sessionStorage.setItem('token', 'not-a-jwt')
    sessionStorage.setItem('userId', '1')
    sessionStorage.setItem('userName', 'Eve')
    const store = useAuthStore()
    store.initFromStorage()
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
  })

})
