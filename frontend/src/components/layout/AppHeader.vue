<script setup lang="ts">
import { HelpCircle, ShoppingCart, LogIn, LogOut } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/authStore'

const auth = useAuthStore()
</script>

<template>
  <header class="banner" role="banner">
    <h1 class="banner__title">CU STUDENT ASSISTANT</h1>
    <div class="banner__icons">
      <a href="https://www.colorado.edu/registrar" class="header-icon" target="_blank" title="Help">
        <HelpCircle :size="18" aria-hidden="true" />
        <span class="sr-only">Help</span>
      </a>
      <a href="#" class="header-icon" title="Cart">
        <ShoppingCart :size="18" aria-hidden="true" />
        <span class="sr-only">Cart</span>
      </a>
    </div>
    <div class="banner__auth">
      <a v-if="!auth.isAuthenticated" href="#" class="anon-only" @click.prevent="() => {}">
        <LogIn :size="16" aria-hidden="true" />
        Login
      </a>
      <div v-else class="authed-only" style="display: inline-flex; align-items: center; color: #fff; padding: 8px 10px; font-size: 13px;">
        Welcome, <span class="user-name" style="margin-left: 4px;">{{ auth.userName }}</span>
      </div>
    </div>
    <div v-if="auth.isAuthenticated" class="banner__logout_icon">
      <a href="#" class="header-icon logout-btn" @click.prevent="auth.logout()" title="Logout">
        <LogOut :size="16" aria-hidden="true" />
        Logout
      </a>
    </div>
  </header>
</template>
