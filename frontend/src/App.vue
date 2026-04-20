<script setup lang="ts">
import { RouterView } from 'vue-router'
import ChatWindow from '@/components/chat/ChatWindow.vue'
import Toast from '@/components/layout/Toast.vue'
</script>

<template>
  <RouterView />
  <ChatWindow />
  <Toast />
</template>
