import { describe, it, expect } from 'vitest'
import { useCourseStore } from './courseStore'

// test-setup.ts calls setActivePinia(createPinia()) before each test

describe('courseStore', () => {
  it('starts with correct initial state', () => {
    const store = useCourseStore()
    expect(store.courses).toEqual([])
    expect(store.total).toBe(0)
    expect(store.offset).toBe(0)
    expect(store.limit).toBe(50)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
    expect(store.expandedCode).toBeNull()
    expect(store.hasSearched).toBe(false)
    expect(store.activeFilters).toEqual({ dept: '', level: '', credits: '' })
    expect(store.selectedCourse).toBeNull()
  })

  it('setCourses populates courses and total', () => {
    const store = useCourseStore()
    const items = [{ code: 'CSCI1300', title: 'Intro CS' }] as any[]
    store.setCourses(items, 42)
    expect(store.courses).toEqual(items)
    expect(store.total).toBe(42)
  })

  it('selectCourse sets selectedCourse; null clears it', () => {
    const store = useCourseStore()
    const course = { code: 'CSCI1300', title: 'Intro CS' } as any
    store.selectCourse(course)
    expect(store.selectedCourse).toEqual(course)
    store.selectCourse(null)
    expect(store.selectedCourse).toBeNull()
  })

  it('setLoading toggles loading', () => {
    const store = useCourseStore()
    store.setLoading(true)
    expect(store.loading).toBe(true)
    store.setLoading(false)
    expect(store.loading).toBe(false)
  })

  it('setError sets error string; null clears it', () => {
    const store = useCourseStore()
    store.setError('Something went wrong')
    expect(store.error).toBe('Something went wrong')
    store.setError(null)
    expect(store.error).toBeNull()
  })

  it('setActiveFilters stores filter values', () => {
    const store = useCourseStore()
    store.setActiveFilters({ dept: 'CSCI', level: '3000', credits: '3' })
    expect(store.activeFilters).toEqual({ dept: 'CSCI', level: '3000', credits: '3' })
  })

  it('toggleExpanded sets expandedCode; same code sets null; different code switches', () => {
    const store = useCourseStore()
    store.toggleExpanded('CSCI1300')
    expect(store.expandedCode).toBe('CSCI1300')
    store.toggleExpanded('CSCI1300')
    expect(store.expandedCode).toBeNull()
    store.toggleExpanded('CSCI1300')
    store.toggleExpanded('CSCI2270')
    expect(store.expandedCode).toBe('CSCI2270')
  })

  it('setHasSearched toggles hasSearched', () => {
    const store = useCourseStore()
    store.setHasSearched(true)
    expect(store.hasSearched).toBe(true)
    store.setHasSearched(false)
    expect(store.hasSearched).toBe(false)
  })

  it('resetPage sets offset to 0', () => {
    const store = useCourseStore()
    store.advancePage(1)
    expect(store.offset).toBe(50)
    store.resetPage()
    expect(store.offset).toBe(0)
  })

  it('advancePage(1) increments offset by limit; advancePage(-1) decrements, clamped to 0', () => {
    const store = useCourseStore()
    store.advancePage(1)
    expect(store.offset).toBe(50)
    store.advancePage(1)
    expect(store.offset).toBe(100)
    store.advancePage(-1)
    expect(store.offset).toBe(50)
    store.advancePage(-1)
    expect(store.offset).toBe(0)
    store.advancePage(-1)
    expect(store.offset).toBe(0)
  })
})
