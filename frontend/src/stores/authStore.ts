import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const isAuthenticated = ref(false)
  const userName = ref('')

  function login(name: string) {
    isAuthenticated.value = true
    userName.value = name
  }

  function logout() {
    isAuthenticated.value = false
    userName.value = ''
  }

  return { isAuthenticated, userName, login, logout }
})
