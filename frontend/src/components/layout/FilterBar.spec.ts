import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FilterBar from './FilterBar.vue'

describe('FilterBar', () => {
  it('renders the form controls', () => {
    const wrapper = mount(FilterBar)
    expect(wrapper.findAll('input,select').length).toBeGreaterThan(0)
  })

  it('emits search event when form is submitted', async () => {
    const wrapper = mount(FilterBar)
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('search')).toBeTruthy()
    const [filters] = wrapper.emitted('search')![0] as [Record<string, string>]
    expect(filters).toHaveProperty('dept')
    expect(filters.dept).toBe('CSCI')
  })

  it('emits search with empty filters on submit without input', async () => {
    const wrapper = mount(FilterBar)
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('search')).toBeTruthy()
  })
})
