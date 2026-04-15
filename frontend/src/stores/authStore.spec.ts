import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useAuthStore } from './authStore'

// test-setup.ts calls setActivePinia(createPinia()) before each test

beforeEach(() => localStorage.clear())
afterEach(() => localStorage.clear())

describe('authStore', () => {
  it('starts unauthenticated with null token and userId', () => {
    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(false)
    expect(store.userName).toBe('')
    expect(store.token).toBeNull()
    expect(store.userId).toBeNull()
  })

  it('setAuth updates state and persists to localStorage', () => {
    const store = useAuthStore()
    store.setAuth('jwt-abc', 7, 'Alice')
    expect(store.isAuthenticated).toBe(true)
    expect(store.userName).toBe('Alice')
    expect(store.token).toBe('jwt-abc')
    expect(store.userId).toBe(7)
    expect(localStorage.getItem('token')).toBe('jwt-abc')
    expect(localStorage.getItem('userId')).toBe('7')
    expect(localStorage.getItem('userName')).toBe('Alice')
  })

  it('logout clears state and removes from localStorage', () => {
    const store = useAuthStore()
    store.setAuth('jwt-abc', 7, 'Alice')
    store.logout()
    expect(store.isAuthenticated).toBe(false)
    expect(store.userName).toBe('')
    expect(store.token).toBeNull()
    expect(store.userId).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('userId')).toBeNull()
    expect(localStorage.getItem('userName')).toBeNull()
  })

  // header.payload.sig — payload = {"exp":9999999999} (year 2286, never expires in tests)
  const validJwt = 'eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjk5OTk5OTk5OTl9.sig'
  // payload = {"exp":1} (epoch + 1 second — always expired)
  const expiredJwt = 'eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjF9.sig'

  it('initFromStorage restores auth state from localStorage for a valid token', () => {
    localStorage.setItem('token', validJwt)
    localStorage.setItem('userId', '99')
    localStorage.setItem('userName', 'Bob')
    const store = useAuthStore()
    store.initFromStorage()
    expect(store.isAuthenticated).toBe(true)
    expect(store.token).toBe(validJwt)
    expect(store.userId).toBe(99)
    expect(store.userName).toBe('Bob')
  })

  it('initFromStorage does nothing when localStorage is empty', () => {
    const store = useAuthStore()
    store.initFromStorage()
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
  })

  it('initFromStorage calls logout for an expired token', () => {
    localStorage.setItem('token', expiredJwt)
    localStorage.setItem('userId', '99')
    localStorage.setItem('userName', 'Bob')
    const store = useAuthStore()
    store.initFromStorage()
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('initFromStorage calls logout for a malformed token', () => {
    localStorage.setItem('token', 'not-a-jwt')
    localStorage.setItem('userId', '1')
    localStorage.setItem('userName', 'Eve')
    const store = useAuthStore()
    store.initFromStorage()
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
  })
})
