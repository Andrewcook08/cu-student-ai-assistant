import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import RegisterModal from './RegisterModal.vue'
import * as authApi from '@/services/authApi'

function mountModal() {
  return mount(RegisterModal, {
    global: { plugins: [createPinia()] },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('RegisterModal', () => {
  it('renders step 1 with email, password, name fields and a Create Account button', () => {
    const wrapper = mountModal()
    expect(wrapper.find('input[type="email"]').exists()).toBe(true)
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
    expect(wrapper.find('input[name="name"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Create Account')
  })

  it('password field has autocomplete="new-password"', () => {
    const wrapper = mountModal()
    expect(wrapper.find('input[type="password"]').attributes('autocomplete')).toBe('new-password')
  })

  it('shows password strength indicator when password is non-empty', async () => {
    const wrapper = mountModal()
    await wrapper.find('input[type="password"]').setValue('short')
    expect(wrapper.find('[data-testid="password-strength"]').exists()).toBe(true)
  })

  it('emits close when Cancel button is clicked', async () => {
    const wrapper = mountModal()
    await wrapper.find('[data-testid="cancel-btn"]').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('shows server error as plain text (never innerHTML) when registration fails', async () => {
    vi.spyOn(authApi, 'register').mockRejectedValue(new Error('<script>alert(1)</script>'))
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('secure-pass-12')
    await wrapper.find('input[name="name"]').setValue('Alice')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const errorEl = wrapper.find('[data-testid="error-msg"]')
    expect(errorEl.exists()).toBe(true)
    // text content contains the literal string (rendered as text, not HTML)
    expect(errorEl.element.textContent).toContain('<script>')
    // but no actual <script> tag was injected into the DOM
    expect(wrapper.find('script').exists()).toBe(false)
  })

  it('moves to step 2 after successful registration and shows program dropdown', async () => {
    vi.spyOn(authApi, 'register').mockResolvedValue({ token: 'tok', user_id: 1 })
    vi.spyOn(authApi, 'fetchPrograms').mockResolvedValue([
      { id: 1, name: 'Computer Science BS', type: 'major', total_credits: 120 },
    ])
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('secure-pass-12')
    await wrapper.find('input[name="name"]').setValue('Alice')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('select[name="program"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Computer Science BS')
  })

  it('emits close after clicking Finish on step 2', async () => {
    vi.spyOn(authApi, 'register').mockResolvedValue({ token: 'tok', user_id: 1 })
    vi.spyOn(authApi, 'fetchPrograms').mockResolvedValue([
      { id: 1, name: 'CS BS', type: 'major', total_credits: 120 },
    ])
    vi.spyOn(authApi, 'updateCompletedCourses').mockResolvedValue(undefined)
    const wrapper = mountModal()
    await wrapper.find('input[type="email"]').setValue('a@b.com')
    await wrapper.find('input[type="password"]').setValue('secure-pass-12')
    await wrapper.find('input[name="name"]').setValue('Alice')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    await wrapper.find('[data-testid="finish-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('close')).toBeTruthy()
  })
})
