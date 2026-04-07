import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FilterBar from './FilterBar.vue'

describe('FilterBar', () => {
  it('renders the form controls', () => {
    const wrapper = mount(FilterBar)
    expect(wrapper.findAll('input,select').length).toBeGreaterThan(0)
  })

  it('does not render a time input', () => {
    const wrapper = mount(FilterBar)
    expect(wrapper.find('#filter-time').exists()).toBe(false)
  })

  it('does not offer law or non-credit level options', () => {
    const wrapper = mount(FilterBar)
    const levelValues = wrapper
      .findAll('#filter-level option')
      .map((o) => (o.element as HTMLOptionElement).value)
    expect(levelValues).not.toContain('law')
    expect(levelValues).not.toContain('non-credit')
    expect(levelValues).toEqual(
      expect.arrayContaining(['', 'undergrad-lower', 'undergrad-upper', 'graduate']),
    )
  })

  it('emits search with dept value when submitted', async () => {
    const wrapper = mount(FilterBar)
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('form').trigger('submit')
    const payloads = wrapper.emitted('search')
    expect(payloads).toBeTruthy()
    const [filters] = payloads![0] as [Record<string, string>]
    expect(filters.dept).toBe('CSCI')
  })

  it('emits exactly { dept, level, credits } with no extra fields', async () => {
    const wrapper = mount(FilterBar)
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('select#filter-level').setValue('undergrad-lower')
    await wrapper.find('select#filter-credits').setValue('3')
    await wrapper.find('form').trigger('submit')
    const [filters] = wrapper.emitted('search')![0] as [Record<string, string>]
    expect(Object.keys(filters).sort()).toEqual(['credits', 'dept', 'level'])
    expect(filters).toEqual({ dept: 'CSCI', level: 'undergrad-lower', credits: '3' })
  })

  it('emits search on submit without any input', async () => {
    const wrapper = mount(FilterBar)
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('search')).toBeTruthy()
  })
})
