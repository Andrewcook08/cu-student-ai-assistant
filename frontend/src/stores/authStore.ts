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
    localStorage.setItem('token', newToken)
    localStorage.setItem('userId', String(newUserId))
    localStorage.setItem('userName', name)
  }

  function logout() {
    isAuthenticated.value = false
    userName.value = ''
    token.value = null
    userId.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('userId')
    localStorage.removeItem('userName')
  }

  function isTokenExpired(rawToken: string): boolean {
    try {
      const parts = rawToken.split('.')
      if (parts.length !== 3) return true
      const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))) as Record<string, unknown>
      if (typeof payload.exp !== 'number') return false
      return payload.exp * 1000 < Date.now()
    } catch {
      return true
    }
  }

  function initFromStorage() {
    const storedToken = localStorage.getItem('token')
    const storedUserId = localStorage.getItem('userId')
    const storedName = localStorage.getItem('userName')
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
