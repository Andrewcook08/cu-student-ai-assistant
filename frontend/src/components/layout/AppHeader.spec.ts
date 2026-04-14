import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import AppHeader from './AppHeader.vue'

function mountHeader() {
  return mount(AppHeader, {
    global: { plugins: [createPinia()] },
  })
}

describe('AppHeader', () => {
  it('renders the banner element', () => {
    const wrapper = mountHeader()
    expect(wrapper.find('header.banner').exists()).toBe(true)
  })

  it('displays the app title', () => {
    const wrapper = mountHeader()
    expect(wrapper.text()).toContain('CU STUDENT ASSISTANT')
  })

  it('shows Login link when not authenticated', () => {
    const wrapper = mountHeader()
    expect(wrapper.text()).toContain('Login')
  })

  it('clicking Login link shows RegisterModal', async () => {
    const wrapper = mountHeader()
    await wrapper.find('button.anon-only').trigger('click')
    expect(wrapper.findComponent({ name: 'RegisterModal' }).exists()).toBe(true)
  })
})
