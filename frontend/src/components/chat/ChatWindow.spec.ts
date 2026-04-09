import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '@/stores/chatStore'
import ChatWindow from './ChatWindow.vue'

// Mock useChat so no real WebSocket is opened during component tests
vi.mock('@/composables/useChat', () => ({
  useChat: () => ({
    connect: vi.fn(),
    send: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

function mountWindow() {
  const pinia = createPinia()
  setActivePinia(pinia)  // ensure useChatStore() resolves against the same pinia the component uses
  return {
    wrapper: mount(ChatWindow, { global: { plugins: [pinia] } }),
    store: useChatStore(),
  }
}

describe('ChatWindow', () => {
  it('renders the collapsed bubble by default', () => {
    const { wrapper } = mountWindow()
    expect(wrapper.find('.chat-bubble').exists()).toBe(true)
    expect(wrapper.find('.chat-panel').exists()).toBe(false)
  })

  it('expands when bubble is clicked', async () => {
    const { wrapper } = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-panel').exists()).toBe(true)
  })

  it('collapses again when header is clicked', async () => {
    const { wrapper } = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')
    await wrapper.find('.chat-panel__header').trigger('click')
    expect(wrapper.find('.chat-panel').exists()).toBe(false)
  })

  it('messages area is present and empty on fresh open', async () => {
    const { wrapper } = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-panel__messages').exists()).toBe(true)
    // No mock messages pre-loaded — live connection populates them
    expect(wrapper.findAll('.chat-message')).toHaveLength(0)
  })

  it('shows reconnecting banner when store.isReconnecting is true', async () => {
    const { wrapper, store } = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-reconnecting').exists()).toBe(false)

    store.setReconnecting(true)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.chat-reconnecting').exists()).toBe(true)
    expect(wrapper.find('.chat-reconnecting').text()).toBe('Reconnecting...')
  })

  it('disables ChatInput when connectionError is set', async () => {
    const { wrapper, store } = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')

    store.setError('Authentication failed. Please log in again.')
    await wrapper.vm.$nextTick()

    const input = wrapper.findComponent({ name: 'ChatInput' })
    expect(input.props('disabled')).toBe(true)
  })

  it('disables ChatInput when isTyping is true', async () => {
    const { wrapper, store } = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')

    store.setTyping(true)
    await wrapper.vm.$nextTick()

    const input = wrapper.findComponent({ name: 'ChatInput' })
    expect(input.props('disabled')).toBe(true)
  })
})
