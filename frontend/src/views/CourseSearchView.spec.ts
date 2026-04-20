import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import CourseSearchView from './CourseSearchView.vue'
import * as courseApi from '@/services/courseApi'

beforeEach(() => {
  vi.restoreAllMocks()
})

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

  it('shows course rows after a successful fetch', async () => {
    vi.spyOn(courseApi, 'fetchCourses').mockResolvedValueOnce({
      items: [{ code: 'CSCI 1300', title: 'Intro CS', credits: '3', dept: 'CSCI', sections: [] }],
      total: 1,
      offset: 0,
      limit: 50,
    })

    const wrapper = mountView()
    await wrapper.find('select#filter-dept').setValue('CSCI')
    // Trigger search via FilterBar's submit event
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('CSCI 1300')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('shows pagination footer with range and total after a search', async () => {
    vi.spyOn(courseApi, 'fetchCourses').mockResolvedValueOnce({
      items: Array.from({ length: 50 }, (_, i) => ({
        code: `CSCI ${1000 + i}`,
        title: `Course ${i}`,
        credits: '3',
        dept: 'CSCI',
        sections: [],
      })),
      total: 200,
      offset: 0,
      limit: 50,
    })

    const wrapper = mountView()
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('.pagination__info').text()).toContain('Showing 1–50 of 200')
  })

  it('Prev is disabled on the first page, Next is enabled when more results exist', async () => {
    vi.spyOn(courseApi, 'fetchCourses').mockResolvedValueOnce({
      items: Array.from({ length: 50 }, (_, i) => ({
        code: `CSCI ${1000 + i}`,
        title: `C${i}`,
        credits: '3',
        dept: 'CSCI',
        sections: [],
      })),
      total: 200,
      offset: 0,
      limit: 50,
    })

    const wrapper = mountView()
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const buttons = wrapper.findAll('.pagination__btn')
    expect(buttons).toHaveLength(2)
    const [prev, next] = buttons
    expect(prev.text()).toBe('Prev')
    expect((prev.element as HTMLButtonElement).disabled).toBe(true)
    expect(next.text()).toBe('Next')
    expect((next.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('Next advances offset and calls fetch with the preserved filter shape', async () => {
    const spy = vi.spyOn(courseApi, 'fetchCourses').mockResolvedValue({
      items: Array.from({ length: 50 }, (_, i) => ({
        code: `CSCI ${1000 + i}`,
        title: `C${i}`,
        credits: '3',
        dept: 'CSCI',
        sections: [],
      })),
      total: 200,
      offset: 0,
      limit: 50,
    })

    const wrapper = mountView()
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const next = wrapper.findAll('.pagination__btn')[1]
    await next.trigger('click')
    await flushPromises()

    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ dept: 'CSCI', offset: 50, limit: 50 }),
    )
    expect(wrapper.find('.pagination__info').text()).toContain('Showing 51–100 of 200')
  })

  it('Next is disabled when all results fit on one page', async () => {
    vi.spyOn(courseApi, 'fetchCourses').mockResolvedValueOnce({
      items: Array.from({ length: 10 }, (_, i) => ({
        code: `CSCI ${2000 + i}`,
        title: `C${i}`,
        credits: '3',
        dept: 'CSCI',
        sections: [],
      })),
      total: 10,
      offset: 0,
      limit: 50,
    })

    const wrapper = mountView()
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const [prev, next] = wrapper.findAll('.pagination__btn')
    expect((prev.element as HTMLButtonElement).disabled).toBe(true)
    expect((next.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('forwards level filter into the fetch call', async () => {
    const spy = vi.spyOn(courseApi, 'fetchCourses').mockResolvedValueOnce({
      items: [],
      total: 0,
      offset: 0,
      limit: 50,
    })

    const wrapper = mountView()
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('select#filter-level').setValue('undergrad-lower')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ dept: 'CSCI', level: 'undergrad-lower' }),
    )
  })

  it('shows error toast and no course rows on fetch failure', async () => {
    vi.spyOn(courseApi, 'fetchCourses').mockRejectedValueOnce(new Error('API unavailable'))

    const wrapper = mountView()
    await wrapper.find('select#filter-dept').setValue('CSCI')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const alert = wrapper.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('API unavailable')
    // Must not silently display mock/fallback data — table is empty
    expect(wrapper.findAll('tbody tr').length).toBe(0)
  })
})
