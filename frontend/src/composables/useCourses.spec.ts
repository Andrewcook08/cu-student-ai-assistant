import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCourses } from './useCourses'
import * as courseApi from '@/services/courseApi'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('useCourses', () => {
  it('fetch success populates courses and total', async () => {
    vi.spyOn(courseApi, 'fetchCourses').mockResolvedValueOnce({
      items: [{ code: 'CSCI 1300', title: 'CS 1', credits: '3', dept: 'CSCI', sections: [] }],
      total: 1,
      offset: 0,
      limit: 50,
    })

    const { courses, total, loading, error, fetch } = useCourses()
    await fetch()

    expect(courses.value).toHaveLength(1)
    expect(courses.value[0].code).toBe('CSCI 1300')
    expect(total.value).toBe(1)
    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
  })

  it('fetch failure sets error and does NOT fall back to mock data', async () => {
    vi.spyOn(courseApi, 'fetchCourses').mockRejectedValueOnce(new Error('Network error'))

    const { courses, error, loading, fetch } = useCourses()
    await fetch()

    // Must surface the error — not silently return mock courses
    expect(error.value).toBe('Network error')
    // Courses must be empty after failure, never populated with mock data
    expect(courses.value).toHaveLength(0)
    expect(loading.value).toBe(false)
  })

  it('loading is true during fetch and false after', async () => {
    let resolveFn!: (v: unknown) => void
    vi.spyOn(courseApi, 'fetchCourses').mockReturnValueOnce(
      new Promise((res) => { resolveFn = res })
    )

    const { loading, fetch } = useCourses()
    const fetchPromise = fetch()
    expect(loading.value).toBe(true)
    resolveFn({ items: [], total: 0, offset: 0, limit: 50 })
    await fetchPromise
    expect(loading.value).toBe(false)
  })
})
