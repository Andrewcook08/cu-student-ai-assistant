<script setup lang="ts">
import { ref } from 'vue'
import { HelpCircle, ShoppingCart, LogIn, LogOut } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/authStore'
import LoginModal from '@/components/auth/LoginModal.vue'
import RegisterModal from '@/components/auth/RegisterModal.vue'

const auth = useAuthStore()
const showLoginModal = ref(false)
const showRegisterModal = ref(false)

function openLogin() {
  showRegisterModal.value = false
  showLoginModal.value = true
}

function openRegister() {
  showLoginModal.value = false
  showRegisterModal.value = true
}

function closeAll() {
  showLoginModal.value = false
  showRegisterModal.value = false
}
</script>

<template>
  <header class="banner" role="banner">
    <h1 class="banner__title">CU STUDENT ASSISTANT</h1>
    <div class="banner__icons">
      <a
        href="https://www.colorado.edu/registrar"
        class="header-icon"
        target="_blank"
        rel="noopener noreferrer"
        title="Help"
      >
        <HelpCircle :size="18" aria-hidden="true" />
        <span class="sr-only">Help</span>
      </a>
      <button type="button" class="header-icon" title="Cart" aria-label="Cart">
        <ShoppingCart :size="18" aria-hidden="true" />
        <span class="sr-only">Cart</span>
      </button>
    </div>
    <div class="banner__auth">
      <button
        v-if="!auth.isAuthenticated"
        type="button"
        class="anon-only"
        aria-haspopup="dialog"
        @click.prevent="openLogin"
      >
        <LogIn :size="16" aria-hidden="true" />
        Login
      </button>
      <div v-else class="banner__auth-welcome">
        Welcome, <span class="user-name" style="margin-left: 4px;">{{ auth.userName }}</span>
      </div>
    </div>
    <div v-if="auth.isAuthenticated" class="banner__logout_icon">
      <button type="button" class="header-icon logout-btn" @click="auth.logout()" title="Logout">
        <LogOut :size="16" aria-hidden="true" />
        Logout
      </button>
    </div>
  </header>

  <LoginModal
    v-if="showLoginModal"
    @close="closeAll"
    @switch-to-register="openRegister"
  />
  <RegisterModal
    v-if="showRegisterModal"
    @close="closeAll"
    @switch-to-login="openLogin"
  />
</template>

<style scoped>
.banner__auth-welcome {
  display: inline-flex;
  align-items: center;
  color: #fff;
  padding: 8px 10px;
  font-size: 13px;
}
</style>
