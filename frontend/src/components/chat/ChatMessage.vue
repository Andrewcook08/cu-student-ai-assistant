<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import type { ChatMessage } from '@/types/index'
import StructuredResponse from './StructuredResponse.vue'
import SuggestedActions from './SuggestedActions.vue'
import type { Action } from '@/types/index'

const props = defineProps<{
  message: ChatMessage
}>()

const emit = defineEmits<{
  actionSelected: [action: Action]
}>()

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const renderedContent = computed(() => {
  const text = props.message.content ?? props.message.reply ?? ''
  return DOMPurify.sanitize(md.render(text))
})

const isUser = computed(() => props.message.role === 'user')
</script>

<template>
  <div :class="['chat-message', isUser ? 'chat-message--user' : 'chat-message--ai']">
    <!-- Markdown content -->
    <div
      v-if="message.content || message.reply"
      class="chat-message__body"
      v-html="renderedContent"
    />
    <!-- Structured course cards -->
    <StructuredResponse
      v-if="message.structured_data && message.structured_data.length > 0"
      :cards="message.structured_data"
    />
    <!-- Suggested action buttons -->
    <SuggestedActions
      v-if="message.suggested_actions && message.suggested_actions.length > 0"
      :actions="message.suggested_actions"
      @action-selected="emit('actionSelected', $event)"
    />
  </div>
</template>

<style scoped>
.chat-message {
  max-width: 85%;
  display: flex;
  flex-direction: column;
}
.chat-message--user {
  align-self: flex-end;
}
.chat-message--ai {
  align-self: flex-start;
}
.chat-message__body {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}
.chat-message--user .chat-message__body {
  background: #000;
  color: #CFB87C;
  border-bottom-right-radius: 3px;
}
.chat-message--ai .chat-message__body {
  background: #fff;
  color: #333;
  border: 1px solid #ddd;
  border-bottom-left-radius: 3px;
}

/* Markdown rendering styles */
.chat-message__body :deep(p) {
  margin-bottom: 6px;
}
.chat-message__body :deep(p:last-child) {
  margin-bottom: 0;
}
.chat-message__body :deep(ul), .chat-message__body :deep(ol) {
  padding-left: 18px;
  margin-bottom: 6px;
}
.chat-message__body :deep(li) {
  margin-bottom: 2px;
}
.chat-message__body :deep(strong) {
  font-weight: 700;
}
.chat-message__body :deep(em) {
  font-style: italic;
}
.chat-message__body :deep(code) {
  background: #f0f0f0;
  padding: 1px 4px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 12px;
}
.chat-message__body :deep(pre) {
  background: #f0f0f0;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  margin-bottom: 6px;
}
.chat-message__body :deep(a) {
  color: #0277BD;
}
</style>
