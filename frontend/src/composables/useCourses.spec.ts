import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCourses } from './useCourses'
import * as courseApi from '@/services/courseApi'
import type { Course, PaginatedResponse } from '@/types/index'

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

  it('threads level filter through to fetchCourses', async () => {
    const spy = vi.spyOn(courseApi, 'fetchCourses').mockResolvedValue({
      items: [],
      total: 0,
      offset: 0,
      limit: 50,
    })

    const { fetch } = useCourses()
    await fetch({ dept: 'CSCI', level: 'undergrad-lower' })

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ dept: 'CSCI', level: 'undergrad-lower', offset: 0, limit: 50 }),
    )
  })

  it('nextPage advances offset and preserves filters', async () => {
    const spy = vi.spyOn(courseApi, 'fetchCourses').mockResolvedValue({
      items: [],
      total: 200,
      offset: 0,
      limit: 50,
    })

    const { fetch, nextPage, offset } = useCourses()
    await fetch({ dept: 'CSCI', level: 'undergrad-lower' })
    await nextPage({ dept: 'CSCI', level: 'undergrad-lower' })

    expect(offset.value).toBe(50)
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ dept: 'CSCI', level: 'undergrad-lower', offset: 50, limit: 50 }),
    )
  })

  it('prevPage decreases offset and preserves filters', async () => {
    const spy = vi.spyOn(courseApi, 'fetchCourses').mockResolvedValue({
      items: [],
      total: 200,
      offset: 0,
      limit: 50,
    })

    const { fetch, nextPage, prevPage, offset } = useCourses()
    await fetch({ dept: 'CSCI' })
    await nextPage({ dept: 'CSCI' })
    await prevPage({ dept: 'CSCI' })

    expect(offset.value).toBe(0)
    expect(spy).toHaveBeenLastCalledWith(
      expect.objectContaining({ dept: 'CSCI', offset: 0, limit: 50 }),
    )
  })

  it('resetPage zeroes the offset without calling the api', () => {
    const spy = vi.spyOn(courseApi, 'fetchCourses')
    const { offset, resetPage } = useCourses()
    offset.value = 100
    resetPage()
    expect(offset.value).toBe(0)
    expect(spy).not.toHaveBeenCalled()
  })

  it('loading is true during fetch and false after', async () => {
    let resolveFn!: (v: PaginatedResponse<Course>) => void
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
