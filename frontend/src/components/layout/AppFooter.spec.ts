import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppFooter from './AppFooter.vue'

describe('AppFooter', () => {
  it('renders the footer element', () => {
    const wrapper = mount(AppFooter)
    expect(wrapper.find('footer').exists()).toBe(true)
  })

  it('contains copyright text', () => {
    const wrapper = mount(AppFooter)
    expect(wrapper.text()).toContain('University of Colorado Boulder')
  })
})
