import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ChatMessage from './ChatMessage.vue'
import type { ChatMessage as ChatMessageType } from '@/types/index'

function mountMsg(message: ChatMessageType) {
  return mount(ChatMessage, {
    props: { message },
    global: { plugins: [createPinia()] },
  })
}

describe('ChatMessage', () => {
  it('renders user messages right-aligned', () => {
    const wrapper = mountMsg({ role: 'user', content: 'Hello' })
    expect(wrapper.find('.chat-message--user').exists()).toBe(true)
  })

  it('renders assistant messages left-aligned', () => {
    const wrapper = mountMsg({ role: 'assistant', reply: 'Hi there!' })
    expect(wrapper.find('.chat-message--ai').exists()).toBe(true)
  })

  it('renders bold markdown', () => {
    const wrapper = mountMsg({ role: 'assistant', reply: '**bold text**' })
    expect(wrapper.html()).toContain('<strong>bold text</strong>')
  })

  it('renders fenced code blocks', () => {
    const wrapper = mountMsg({ role: 'assistant', reply: '```\ncode here\n```' })
    expect(wrapper.html()).toContain('<code>')
  })

  it('renders lists', () => {
    const wrapper = mountMsg({ role: 'assistant', reply: '- item one\n- item two' })
    expect(wrapper.html()).toContain('<li>')
  })

  it('XSS: does not render script tags from user content', () => {
    const xss = '<script>alert(1)<\/script>'
    const wrapper = mountMsg({ role: 'assistant', reply: xss })
    expect(wrapper.html()).not.toContain('<script>')
  })

  it('XSS: strips onerror attribute from img tags', () => {
    const xss = '<img src=x onerror=alert(1)>'
    const wrapper = mountMsg({ role: 'assistant', reply: xss })
    // html: false in markdown-it escapes raw HTML; DOMPurify strips any that slips through.
    // The onerror should NOT appear as an actual HTML attribute (only possibly as escaped text).
    const dom = new DOMParser().parseFromString(wrapper.html(), 'text/html')
    const imgs = dom.querySelectorAll('img')
    imgs.forEach((img) => {
      expect(img.hasAttribute('onerror')).toBe(false)
    })
  })

  it('renders structured data (CourseCards) when present', () => {
    const wrapper = mountMsg({
      role: 'assistant',
      reply: 'Here are some courses:',
      structured_data: [
        { code: 'CSCI 1300', title: 'Intro to CS', credits: '3' },
      ],
    })
    expect(wrapper.text()).toContain('CSCI 1300')
  })
})
