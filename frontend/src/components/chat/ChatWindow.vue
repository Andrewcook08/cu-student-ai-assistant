<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { MessageCircle, X } from 'lucide-vue-next'
import ChatInput from './ChatInput.vue'
import ChatMessage from './ChatMessage.vue'
import type { Action } from '@/types/index'
import { useChatStore } from '@/stores/chatStore'
import { useChat } from '@/composables/useChat'

const isOpen = ref(false)
const messagesEnd = ref<HTMLElement | null>(null)
const store = useChatStore()
const { connect, send } = useChat()

function toggle() {
  isOpen.value = !isOpen.value
}

function sendMessage(text: string) {
  send(text)
}

function handleActionSelected(action: Action) {
  send(action.label, {
    action_response: { type: action.type, value: action.label },
  })
}

onMounted(() => connect())

watch(
  () => store.messages.length,
  async () => {
    await nextTick()
    messagesEnd.value?.scrollIntoView({ behavior: 'smooth' })
  },
)
</script>

<template>
  <!-- Collapsed: icon button only -->
  <div v-if="!isOpen" class="chat-bubble" @click="toggle" title="Open AI assistant">
    <MessageCircle :size="24" />
  </div>

  <!-- Expanded: full chat panel -->
  <div v-else class="chat-panel">
    <div class="chat-panel__header" @click="toggle">
      <span class="chat-panel__title">CU AI Advisor</span>
      <button class="chat-panel__close" title="Close chat" @click.stop="toggle">
        <X :size="16" />
      </button>
    </div>

    <div v-if="store.isReconnecting" class="chat-reconnecting">Reconnecting...</div>

    <div class="chat-panel__messages">
      <ChatMessage
        v-for="(msg, i) in store.messages"
        :key="i"
        :message="msg"
        @action-selected="handleActionSelected"
      />
      <div v-if="store.isTyping" class="chat-msg chat-msg--ai chat-msg--typing">
        <span></span><span></span><span></span>
      </div>
      <div ref="messagesEnd" />
    </div>

    <ChatInput
      :disabled="store.isTyping || !!store.connectionError"
      @send="sendMessage"
    />
  </div>
</template>

<style scoped>
/* Collapsed bubble */
.chat-bubble {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 52px;
  height: 52px;
  background: #000;
  color: #CFB87C;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
  z-index: 1000;
  transition: transform 0.15s, box-shadow 0.15s;
}
.chat-bubble:hover {
  transform: scale(1.06);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.3);
}

/* Expanded panel */
.chat-panel {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 360px;
  height: 520px;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  z-index: 1000;
  overflow: hidden;
}
.chat-panel__header {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 48px;
  background: #000;
  color: #CFB87C;
  cursor: pointer;
  flex-shrink: 0;
}
.chat-panel__title {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.chat-panel__close {
  background: none;
  border: none;
  color: #CFB87C;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 6px;
  border-radius: 3px;
  opacity: 0.85;
  transition: opacity 0.15s;
}
.chat-panel__close:hover { opacity: 1; }

/* Reconnecting banner */
.chat-reconnecting {
  background: #fff8e1;
  color: #795548;
  font-size: 12px;
  text-align: center;
  padding: 4px 12px;
  border-bottom: 1px solid #ffe082;
  flex-shrink: 0;
}

.chat-panel__messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #fafafa;
}

/* Typing indicator */
.chat-msg--typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 14px;
}
.chat-msg--typing span {
  width: 6px;
  height: 6px;
  background: #999;
  border-radius: 50%;
  display: inline-block;
  animation: typing-dot 1.2s infinite ease-in-out;
}
.chat-msg--typing span:nth-child(2) { animation-delay: 0.2s; }
.chat-msg--typing span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing-dot {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.4; }
  40% { transform: scale(1.1); opacity: 1; }
}
</style>
