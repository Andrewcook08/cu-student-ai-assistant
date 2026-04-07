import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatInput from './ChatInput.vue'

describe('ChatInput', () => {
  it('renders a textarea and send button', () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('emits send event on Enter key', async () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    await wrapper.find('textarea').setValue('Hello')
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter', shiftKey: false })
    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')![0]).toEqual(['Hello'])
  })

  it('clears input after send', async () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    const textarea = wrapper.find('textarea')
    await textarea.setValue('Hello')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: false })
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  it('disables textarea when disabled prop is true', () => {
    const wrapper = mount(ChatInput, { props: { disabled: true } })
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
  })

  it('send button is not usable when input is empty', async () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    // Empty input → canSend is false → button has disabled attribute
    await wrapper.find('textarea').setValue('')
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('send button has an accessible name via title', () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    const btn = wrapper.find('button')
    const hasAriaLabel = btn.attributes('aria-label')
    const hasTitle = btn.attributes('title')
    const hasText = btn.text().trim().length > 0
    expect(hasAriaLabel || hasTitle || hasText).toBeTruthy()
  })

  it('textarea has an accessible label', () => {
    const wrapper = mount(ChatInput, { props: { disabled: false } })
    const textarea = wrapper.find('textarea')
    const hasAriaLabel = textarea.attributes('aria-label')
    const hasId = textarea.attributes('id')
    expect(hasAriaLabel || hasId).toBeTruthy()
  })
})
