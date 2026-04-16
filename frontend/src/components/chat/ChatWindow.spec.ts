import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '@/stores/chatStore'
import { useAuthStore } from '@/stores/authStore'
import ChatWindow from './ChatWindow.vue'

// payload = {"sub":1,"exp":9999999999}
const validJwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6OTk5OTk5OTk5OX0.sig'

// Shared mocks so tests can assert connect/disconnect were called.
const chatMocks = {
  connect: vi.fn(),
  send: vi.fn(),
  disconnect: vi.fn(),
}
vi.mock('@/composables/useChat', () => ({
  useChat: () => chatMocks,
}))

beforeEach(() => {
  chatMocks.connect.mockClear()
  chatMocks.send.mockClear()
  chatMocks.disconnect.mockClear()
})

function mountWindow(authenticated = false) {
  const pinia = createPinia()
  setActivePinia(pinia)
  if (authenticated) {
    const authStore = useAuthStore()
    authStore.setAuth(validJwt, 1, 'TestUser')
  }
  return {
    wrapper: mount(ChatWindow, { global: { plugins: [pinia] } }),
    store: useChatStore(),
    authStore: useAuthStore(),
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

  it('collapses again when header is clicked (mousedown + mouseup without drag)', async () => {
    const { wrapper } = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')
    await wrapper.find('.chat-panel__header').trigger('mousedown')
    // No mousemove — triggers toggle on mouseup
    document.dispatchEvent(new MouseEvent('mouseup'))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.chat-panel').exists()).toBe(false)
  })

  it('shows auth gate when not authenticated', async () => {
    const { wrapper } = mountWindow(false)
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('[data-testid="chat-login-btn"]').exists()).toBe(true)
    expect(wrapper.find('.chat-panel__messages').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'ChatInput' }).exists()).toBe(false)
  })

  it('shows chat UI when authenticated', async () => {
    const { wrapper } = mountWindow(true)
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-panel__messages').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'ChatInput' }).exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-login-btn"]').exists()).toBe(false)
  })

  it('messages area is present and empty on fresh open (authenticated)', async () => {
    const { wrapper } = mountWindow(true)
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-panel__messages').exists()).toBe(true)
    expect(wrapper.findAll('.chat-message')).toHaveLength(0)
  })

  it('shows reconnecting banner when store.isReconnecting is true', async () => {
    const { wrapper, store } = mountWindow(true)
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-reconnecting').exists()).toBe(false)

    store.setReconnecting(true)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.chat-reconnecting').exists()).toBe(true)
    expect(wrapper.find('.chat-reconnecting').text()).toBe('Reconnecting...')
  })

  it('disables ChatInput when connectionError is set', async () => {
    const { wrapper, store } = mountWindow(true)
    await wrapper.find('.chat-bubble').trigger('click')

    store.setError('Authentication failed. Please log in again.')
    await wrapper.vm.$nextTick()

    const input = wrapper.findComponent({ name: 'ChatInput' })
    expect(input.props('disabled')).toBe(true)
  })

  it('disables ChatInput when isTyping is true', async () => {
    const { wrapper, store } = mountWindow(true)
    await wrapper.find('.chat-bubble').trigger('click')

    store.setTyping(true)
    await wrapper.vm.$nextTick()

    const input = wrapper.findComponent({ name: 'ChatInput' })
    expect(input.props('disabled')).toBe(true)
  })

  it('calls connect() on mount when already authenticated', () => {
    mountWindow(true)
    expect(chatMocks.connect).toHaveBeenCalled()
    expect(chatMocks.disconnect).not.toHaveBeenCalled()
  })

  it('does NOT call connect() on mount when unauthenticated', () => {
    mountWindow(false)
    expect(chatMocks.connect).not.toHaveBeenCalled()
  })

  it('calls connect() when user logs in after mount', async () => {
    const { wrapper, authStore } = mountWindow(false)
    expect(chatMocks.connect).not.toHaveBeenCalled()
    authStore.setAuth(validJwt, 2, 'Bob')
    await wrapper.vm.$nextTick()
    expect(chatMocks.connect).toHaveBeenCalledTimes(1)
  })

  it('calls disconnect() when user logs out — prevents cross-user WebSocket reuse', async () => {
    const { wrapper, authStore } = mountWindow(true)
    expect(chatMocks.disconnect).not.toHaveBeenCalled()
    authStore.logout()
    await wrapper.vm.$nextTick()
    expect(chatMocks.disconnect).toHaveBeenCalledTimes(1)
  })
})
