<script setup lang="ts">
import { ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { MessageCircle, RefreshCw, X } from 'lucide-vue-next'
import ChatInput from './ChatInput.vue'
import ChatMessage from './ChatMessage.vue'
import type { Action } from '@/types/index'
import { useChatStore } from '@/stores/chatStore'
import { useAuthStore } from '@/stores/authStore'
import { useChat } from '@/composables/useChat'

const isOpen = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const store = useChatStore()
const auth = useAuthStore()
const { connect, disconnect, send, clearConversation } = useChat()

function onClearClick(e: MouseEvent) {
  e.stopPropagation()
  clearConversation()
}

// ── Resize by dragging the header bar upward/leftward ────────
let resizing = false
let dragged = false
let startX = 0
let startY = 0
let startW = 0
let startH = 0

function onResizeStart(e: MouseEvent) {
  // Ignore clicks on the close button
  if ((e.target as HTMLElement).closest('.chat-panel__close')) return
  if (!panelEl.value) return
  e.preventDefault()
  dragged = false
  startX = e.clientX
  startY = e.clientY
  startW = panelEl.value.offsetWidth
  startH = panelEl.value.offsetHeight
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', onResizeEnd)
}

function onResizeMove(e: MouseEvent) {
  if (!panelEl.value) return
  const dx = startX - e.clientX
  const dy = startY - e.clientY
  if (!resizing && (Math.abs(dx) > 4 || Math.abs(dy) > 4)) {
    resizing = true
    dragged = true
  }
  if (!resizing) return
  panelEl.value.style.width = `${Math.max(300, startW + dx)}px`
  panelEl.value.style.height = `${Math.max(320, startH + dy)}px`
}

function onResizeEnd() {
  resizing = false
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
  // If no drag occurred, treat as a click → toggle
  if (!dragged) toggle()
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
})

function toggle() {
  isOpen.value = !isOpen.value
}

function handleActionSelected(action: Action) {
  send(action.label, {
    action_response: { type: action.type, value: action.label },
  })
}

onMounted(() => {
  if (auth.isAuthenticated) connect()
})

watch(
  () => auth.isAuthenticated,
  (loggedIn) => {
    if (loggedIn) {
      connect()
    } else {
      // Tear down the WebSocket so a logged-out user's stale session can't be
      // reused by the next user who logs in on this tab (sessionStorage is
      // per-tab but the WebSocket outlives the logout unless we close it).
      disconnect()
      // Collapse the panel so a subsequent login doesn't re-render into an
      // already-open window with no context. Login is handled by AppHeader.
      isOpen.value = false
    }
  },
)

watch(
  () => {
    const msgs = store.messages
    const last = msgs[msgs.length - 1]
    return [msgs.length, last?.reply?.length ?? 0, store.toolStatus]
  },
  async () => {
    await nextTick()
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  },
)
</script>

<template>
  <!-- Chat is unavailable when logged out. Login is handled by AppHeader,
       so there's no reason to render a bubble the user can only bounce off. -->
  <template v-if="auth.isAuthenticated">
    <!-- Collapsed: icon button only -->
    <div v-if="!isOpen" class="chat-bubble" @click="toggle" title="Open AI assistant">
      <MessageCircle :size="24" />
    </div>

    <!-- Expanded: full chat panel -->
    <div v-else ref="panelEl" class="chat-panel">
      <div class="chat-panel__header" @mousedown="onResizeStart">
        <span class="chat-panel__title">CU AI Advisor</span>
        <button
          class="chat-panel__clear"
          title="Clear conversation"
          data-testid="chat-clear-btn"
          @mousedown.stop
          @click="onClearClick"
        >
          <RefreshCw :size="14" />
        </button>
        <button class="chat-panel__close" title="Close chat" @click.stop="toggle">
          <X :size="16" />
        </button>
      </div>

      <div v-if="store.isReconnecting" class="chat-reconnecting">Reconnecting...</div>

      <div ref="messagesEl" class="chat-panel__messages">
        <ChatMessage
          v-for="(msg, i) in store.messages"
          :key="i"
          :message="msg"
          @action-selected="handleActionSelected"
        />
        <div v-if="store.toolStatus" class="chat-tool-status">
          {{ store.toolStatus }}
        </div>
        <div v-else-if="store.isTyping && !store.isStreaming" class="chat-msg chat-msg--ai chat-msg--typing">
          <span></span><span></span><span></span>
        </div>
      </div>

      <ChatInput
        :disabled="store.isTyping || store.isStreaming || !!store.connectionError"
        @send="send"
      />
    </div>
  </template>
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
  width: 400px;
  height: 560px;
  min-width: 300px;
  min-height: 320px;
  max-width: 90vw;
  max-height: 85vh;
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
  cursor: nw-resize;
  flex-shrink: 0;
  user-select: none;
}
.chat-panel__title {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.chat-panel__close,
.chat-panel__clear {
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
.chat-panel__close:hover,
.chat-panel__clear:hover { opacity: 1; }
.chat-panel__clear { margin-right: 4px; }

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

/* Tool status */
.chat-tool-status {
  align-self: flex-start;
  font-size: 12px;
  font-style: italic;
  padding: 4px 12px;
  background: linear-gradient(
    90deg,
    #aaa 0%,
    #CFB87C 40%,
    #aaa 80%
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
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
