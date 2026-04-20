import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Toast from './Toast.vue'
import { useToastStore } from '@/stores/toastStore'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Toast', () => {
  it('renders nothing when there are no toasts', () => {
    const wrapper = mount(Toast)
    expect(wrapper.find('.toast').exists()).toBe(false)
  })

  it('renders a pushed success toast', async () => {
    const wrapper = mount(Toast)
    const store = useToastStore()
    store.push({ level: 'success', message: 'Saved.' })
    await wrapper.vm.$nextTick()
    const el = wrapper.find('[data-testid="toast-success"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Saved.')
  })

  it('auto-dismisses after the duration', async () => {
    const wrapper = mount(Toast)
    const store = useToastStore()
    store.push({ level: 'info', message: 'Hello', durationMs: 1000 })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="toast-info"]').exists()).toBe(true)

    vi.advanceTimersByTime(1001)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="toast-info"]').exists()).toBe(false)
  })

  it('does not auto-dismiss when durationMs is 0', async () => {
    const wrapper = mount(Toast)
    const store = useToastStore()
    store.push({ level: 'error', message: 'Sticky', durationMs: 0 })
    await wrapper.vm.$nextTick()
    vi.advanceTimersByTime(10_000)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="toast-error"]').exists()).toBe(true)
  })

  it('manual dismiss removes the toast', async () => {
    const wrapper = mount(Toast)
    const store = useToastStore()
    store.push({ level: 'success', message: 'Go away' })
    await wrapper.vm.$nextTick()
    await wrapper.find('.toast__close').trigger('click')
    expect(wrapper.find('[data-testid="toast-success"]').exists()).toBe(false)
  })
})
