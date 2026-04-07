import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ChatWindow from './ChatWindow.vue'

function mountWindow() {
  return mount(ChatWindow, {
    global: { plugins: [createPinia()] },
  })
}

describe('ChatWindow', () => {
  it('renders the collapsed bubble by default', () => {
    const wrapper = mountWindow()
    // Collapsed state: bubble button visible, panel not visible
    expect(wrapper.find('.chat-bubble').exists()).toBe(true)
    expect(wrapper.find('.chat-panel').exists()).toBe(false)
  })

  it('expands when bubble is clicked', async () => {
    const wrapper = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-panel').exists()).toBe(true)
  })

  it('collapses again when header is clicked', async () => {
    const wrapper = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-panel').exists()).toBe(true)
    await wrapper.find('.chat-panel__header').trigger('click')
    expect(wrapper.find('.chat-panel').exists()).toBe(false)
  })

  it('shows initial assistant greeting when expanded', async () => {
    const wrapper = mountWindow()
    await wrapper.find('.chat-bubble').trigger('click')
    expect(wrapper.find('.chat-panel__messages').exists()).toBe(true)
    // Initial greeting message is pre-loaded (class name is chat-msg--ai on this version)
    const hasMsg = wrapper.find('.chat-msg--ai').exists() || wrapper.find('.chat-message--ai').exists()
    expect(hasMsg).toBe(true)
  })
})
