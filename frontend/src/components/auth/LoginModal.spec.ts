import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import LoginModal from './LoginModal.vue'
import * as authApi from '@/services/authApi'

// payload = {"sub":1,"exp":9999999999}
const validJwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6OTk5OTk5OTk5OX0.sig'

const loginOk = {
  access_token: validJwt,
  token_type: 'bearer' as const,
  expires_in: 3600,
  user_id: 1,
  name: 'Test User',
}

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

  it('disables the submit button on mount (empty fields)', () => {
    const wrapper = mountModal()
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeDefined()
  })

  it('keeps submit disabled with a malformed email', async () => {
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('not-an-email')
    await wrapper.find('input[type="password"]').setValue('anything')
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeDefined()
  })

  it('keeps submit disabled with empty password', async () => {
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeDefined()
  })

  it('enables submit when both fields are valid', async () => {
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('anything')
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeUndefined()
  })

  it('shows inline email error after blur on invalid email', async () => {
    const wrapper = mountModal()
    const emailInput = wrapper.find('input[type="email"]')
    await emailInput.setValue('bad')
    await emailInput.trigger('blur')
    expect(wrapper.find('[data-testid="email-error"]').exists()).toBe(true)
  })

  it('does not run the network request when fields are invalid on submit', async () => {
    const loginSpy = vi.spyOn(authApi, 'login').mockResolvedValue(loginOk)
    const wrapper = mountModal()
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(loginSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="email-error"]').exists()).toBe(true)
  })

  it('emits close when Cancel button is clicked', async () => {
    const wrapper = mountModal()
    await wrapper.find('[data-testid="cancel-btn"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('emits close after successful login', async () => {
    vi.spyOn(authApi, 'login').mockResolvedValue(loginOk)
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('p4ssword')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('shows error message (as plain text) on login failure', async () => {
    vi.spyOn(authApi, 'login').mockRejectedValue(new Error('Invalid email or password.'))
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('wrong')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const errorEl = wrapper.find('[data-testid="error-msg"]')
    expect(errorEl.exists()).toBe(true)
    expect(errorEl.element.textContent).toContain('Invalid email or password.')
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

  it('disables inputs + submit button while loading', async () => {
    let resolve!: (v: typeof loginOk) => void
    vi.spyOn(authApi, 'login').mockReturnValue(new Promise(r => { resolve = r }))
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('p4ssword')
    await wrapper.find('form').trigger('submit')
    await nextTick()
    expect(wrapper.find('input[type="email"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('input[type="password"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="submit-btn"]').attributes('disabled')).toBeDefined()
    resolve(loginOk)
    await flushPromises()
  })

  it('emits switch-to-register when the register link is clicked', async () => {
    const wrapper = mountModal()
    await wrapper.find('[data-testid="switch-to-register"]').trigger('click')
    expect(wrapper.emitted('switch-to-register')).toBeTruthy()
  })
})
