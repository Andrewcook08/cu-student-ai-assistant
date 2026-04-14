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

  function initFromStorage() {
    const storedToken = localStorage.getItem('token')
    const storedUserId = localStorage.getItem('userId')
    const storedName = localStorage.getItem('userName')
    if (storedToken && storedUserId) {
      token.value = storedToken
      userId.value = Number(storedUserId)
      userName.value = storedName ?? ''
      isAuthenticated.value = true
    }
  }

  return { isAuthenticated, userName, token, userId, setAuth, logout, initFromStorage }
})
