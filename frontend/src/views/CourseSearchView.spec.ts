import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import CourseSearchView from './CourseSearchView.vue'

function mountView() {
  return mount(CourseSearchView, {
    global: { plugins: [createPinia()] },
  })
}

describe('CourseSearchView', () => {
  it('renders without crashing', () => {
    const wrapper = mountView()
    expect(wrapper.exists()).toBe(true)
  })

  it('renders the header', () => {
    const wrapper = mountView()
    expect(wrapper.find('header').exists()).toBe(true)
  })

  it('renders the filter bar', () => {
    const wrapper = mountView()
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('renders footer', () => {
    const wrapper = mountView()
    expect(wrapper.find('footer').exists()).toBe(true)
  })
})
