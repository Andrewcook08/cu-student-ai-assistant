import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const isAuthenticated = ref(false)
  const userName = ref('')
  const token = ref<string | null>(null)
  const userId = ref<number | null>(null)

  function setAuth(newToken: string, newUserId: number, name: string) {
    token.value = newToken
    userId.value = newUserId
    userName.value = name
    isAuthenticated.value = true
    sessionStorage.setItem('token', newToken)
    sessionStorage.setItem('userId', String(newUserId))
    sessionStorage.setItem('userName', name)
  }

  function logout() {
    isAuthenticated.value = false
    userName.value = ''
    token.value = null
    userId.value = null
    sessionStorage.removeItem('token')
    sessionStorage.removeItem('userId')
    sessionStorage.removeItem('userName')
  }

  function parseTokenPayload(rawToken: string): Record<string, unknown> | null {
    try {
      const parts = rawToken.split('.')
      if (parts.length !== 3) return null
      return JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))) as Record<string, unknown>
    } catch {
      return null
    }
  }

  function isTokenExpired(rawToken: string): boolean {
    const payload = parseTokenPayload(rawToken)
    if (!payload) return true
    if (typeof payload.exp !== 'number') return false
    return payload.exp * 1000 < Date.now()
  }

  function initFromStorage() {
    const storedToken = sessionStorage.getItem('token')
    const storedUserId = sessionStorage.getItem('userId')
    const storedName = sessionStorage.getItem('userName')
    const parsedUserId = storedUserId ? Number(storedUserId) : Number.NaN

    if (
      storedToken &&
      Number.isInteger(parsedUserId) &&
      parsedUserId > 0 &&
      !isTokenExpired(storedToken)
    ) {
      token.value = storedToken
      userId.value = parsedUserId
      userName.value = storedName ?? ''
      isAuthenticated.value = true
      return
    }

    logout()
  }

  return { isAuthenticated, userName, token, userId, setAuth, logout, initFromStorage }
})
