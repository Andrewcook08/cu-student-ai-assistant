import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import LoginModal from './LoginModal.vue'
import * as authApi from '@/services/authApi'

// payload = {"sub":1,"exp":9999999999}
const validJwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6OTk5OTk5OTk5OX0.sig'

function mountModal() {
  return mount(LoginModal, {
    global: { plugins: [createPinia()] },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

describe('LoginModal', () => {
  it('renders email, password fields and a Log In button', () => {
    const wrapper = mountModal()
    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Log In')
  })

  it('password field has autocomplete="current-password"', () => {
    const wrapper = mountModal()
    expect(wrapper.find('input[type="password"]').attributes('autocomplete')).toBe('current-password')
  })

  it('emits close when Cancel button is clicked', async () => {
    const wrapper = mountModal()
    await wrapper.find('[data-testid="cancel-btn"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('emits close after successful login', async () => {
    vi.spyOn(authApi, 'login').mockResolvedValue({ token: validJwt })
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('p4ssword')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('shows error message (as plain text) on login failure', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue(new Error('Invalid credentials'))
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('wrong')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const errorEl = wrapper.find('[data-testid="error-msg"]')
    expect(errorEl.exists()).toBe(true)
    expect(errorEl.element.textContent).toContain('Invalid credentials')
    expect(wrapper.find('script').exists()).toBe(false)
  })

  it('shows server XSS payload as plain text, not injected HTML', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue(new Error('<script>alert(1)</script>'))
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('p')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const errorEl = wrapper.find('[data-testid="error-msg"]')
    expect(errorEl.element.textContent).toContain('<script>')
    expect(wrapper.find('script').exists()).toBe(false)
  })

  it('disables the submit button while loading', async () => {
    let resolve!: (v: { token: string }) => void
    vi.spyOn(authApi, 'login').mockReturnValue(new Promise(r => { resolve = r }))
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('p4ssword')
    await wrapper.find('form').trigger('submit')
    await nextTick()
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
    resolve({ token: validJwt })
  })

  it('emits switch-to-register when the register link is clicked', async () => {
    const wrapper = mountModal()
    await wrapper.find('[data-testid="switch-to-register"]').trigger('click')
    expect(wrapper.emitted('switch-to-register')).toBeTruthy()
  })
})
