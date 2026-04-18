import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchCourses, fetchCourse } from '@/services/courseApi'
import { useAuthStore } from '@/stores/authStore'

function mockFetch(body: unknown, init?: ResponseInit): void {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(body), { status: 200, ...init }),
  )
}

function getLastFetchCall(): [RequestInfo | URL, RequestInit | undefined] {
  const lastCall = vi.mocked(globalThis.fetch).mock.calls.at(-1)
  if (!lastCall) throw new Error('Expected fetch to have been called')
  return [lastCall[0], lastCall[1] as RequestInit | undefined]
}

beforeEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

describe('courseApi', () => {
  describe('fetchCourses', () => {
    it('sends request to /api/courses with no query params when filters are empty', async () => {
      mockFetch({ items: [], total: 0, offset: 0, limit: 50 })
      await fetchCourses()
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.pathname).toBe('/api/courses')
      expect(url.search).toBe('')
    })

    it('sends request with no query params for explicit empty object', async () => {
      mockFetch({ items: [], total: 0, offset: 0, limit: 50 })
      await fetchCourses({})
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.pathname).toBe('/api/courses')
      expect(url.search).toBe('')
    })

    it('includes all filters in query string when every field is set', async () => {
      mockFetch({ items: [], total: 0, offset: 0, limit: 25 })
      await fetchCourses({
        dept: 'CSCI',
        level: 'undergrad-upper',
        instruction_mode: 'In Person',
        status: 'Open',
        credits: '3',
        q: 'algorithms',
        offset: 10,
        limit: 25,
      })
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.searchParams.get('dept')).toBe('CSCI')
      expect(url.searchParams.get('level')).toBe('undergrad-upper')
      expect(url.searchParams.get('instruction_mode')).toBe('In Person')
      expect(url.searchParams.get('status')).toBe('Open')
      expect(url.searchParams.get('credits')).toBe('3')
      expect(url.searchParams.get('q')).toBe('algorithms')
      expect(url.searchParams.get('offset')).toBe('10')
      expect(url.searchParams.get('limit')).toBe('25')
    })

    it('includes only provided filters in query string', async () => {
      mockFetch({ items: [], total: 0, offset: 0, limit: 50 })
      await fetchCourses({ dept: 'MATH', q: 'calculus' })
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.searchParams.get('dept')).toBe('MATH')
      expect(url.searchParams.get('q')).toBe('calculus')
      expect(url.searchParams.has('level')).toBe(false)
      expect(url.searchParams.has('instruction_mode')).toBe(false)
      expect(url.searchParams.has('status')).toBe(false)
      expect(url.searchParams.has('credits')).toBe(false)
      expect(url.searchParams.has('offset')).toBe(false)
      expect(url.searchParams.has('limit')).toBe(false)
    })

    it('omits filters that are empty strings', async () => {
      mockFetch({ items: [], total: 0, offset: 0, limit: 50 })
      await fetchCourses({ dept: '', level: '', q: '' })
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.pathname).toBe('/api/courses')
      expect(url.search).toBe('')
    })

    it('includes offset when value is 0', async () => {
      mockFetch({ items: [], total: 0, offset: 0, limit: 50 })
      await fetchCourses({ offset: 0 })
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.searchParams.get('offset')).toBe('0')
    })

    it('includes limit when value is 0', async () => {
      mockFetch({ items: [], total: 0, offset: 0, limit: 0 })
      await fetchCourses({ limit: 0 })
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.searchParams.get('limit')).toBe('0')
    })

    it('returns parsed JSON body on success', async () => {
      const body = {
        items: [{ code: 'CSCI 1300', title: 'CS 1', credits: '3', dept: 'CSCI', sections: [] }],
        total: 1,
        offset: 0,
        limit: 50,
      }
      mockFetch(body)
      const result = await fetchCourses()
      expect(result.items).toHaveLength(1)
      expect(result.items[0].code).toBe('CSCI 1300')
      expect(result.total).toBe(1)
    })

    it('throws on 500 response', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status: 500 }))
      await expect(fetchCourses()).rejects.toThrow('Failed to fetch courses: 500')
    })

    it('throws on 403 response', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status: 403 }))
      await expect(fetchCourses()).rejects.toThrow('Failed to fetch courses: 403')
    })

    it('attaches Authorization header when store has a token', async () => {
      const store = useAuthStore()
      store.setAuth('my-token', 1, 'Alice')
      mockFetch({ items: [], total: 0, offset: 0, limit: 50 })
      await fetchCourses()
      const [, requestInit] = getLastFetchCall()
      expect((requestInit?.headers as Record<string, string>)['Authorization']).toBe('Bearer my-token')
    })

    it('omits Authorization header when unauthenticated — course list is public', async () => {
      mockFetch({ items: [], total: 0, offset: 0, limit: 50 })
      await fetchCourses({ dept: 'CSCI' })
      const [, requestInit] = getLastFetchCall()
      expect((requestInit?.headers as Record<string, string>)['Authorization']).toBeUndefined()
    })

    it('clears auth state on 401 response', async () => {
      const store = useAuthStore()
      store.setAuth('expired-token', 1, 'Alice')
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 401 }))
      await expect(fetchCourses()).rejects.toThrow('Failed to fetch courses: 401')
      expect(store.isAuthenticated).toBe(false)
    })
  })

  describe('fetchCourse', () => {
    it('sends request to /api/courses/<encoded code>', async () => {
      mockFetch({ code: 'CSCI 1300', title: 'CS 1', credits: '3', dept: 'CSCI', sections: [] })
      await fetchCourse('CSCI 1300')
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.pathname).toBe('/api/courses/CSCI%201300')
    })

    it('URL-encodes special characters in course code', async () => {
      mockFetch({ code: 'TEST/100', title: 'Test', credits: '3', dept: 'TEST', sections: [] })
      await fetchCourse('TEST/100')
      const url = new URL(
        vi.mocked(globalThis.fetch).mock.calls[0][0] as string,
        'http://localhost',
      )
      expect(url.pathname).toBe('/api/courses/TEST%2F100')
    })

    it('returns parsed JSON body on success', async () => {
      const body = { code: 'CSCI 1300', title: 'CS 1', credits: '3', dept: 'CSCI', sections: [] }
      mockFetch(body)
      const result = await fetchCourse('CSCI 1300')
      expect(result.code).toBe('CSCI 1300')
      expect(result.title).toBe('CS 1')
    })

    it('throws "not found" error on 404', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status: 404 }))
      await expect(fetchCourse('FAKE 999')).rejects.toThrow("Course 'FAKE 999' not found")
    })

    it('throws generic error on 500', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status: 500 }))
      await expect(fetchCourse('CSCI 1300')).rejects.toThrow('Failed to fetch course: 500')
    })

    it('throws generic error on 403', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('', { status: 403 }))
      await expect(fetchCourse('CSCI 1300')).rejects.toThrow('Failed to fetch course: 403')
    })

    it('attaches Authorization header for fetchCourse when authenticated', async () => {
      const store = useAuthStore()
      store.setAuth('my-token', 1, 'Alice')
      mockFetch({ code: 'CSCI1300', title: 'Computer Science 1', credits: '4', dept: 'CSCI', sections: [] })
      await fetchCourse('CSCI1300')
      const [, requestInit] = getLastFetchCall()
      expect((requestInit?.headers as Record<string, string>)['Authorization']).toBe('Bearer my-token')
    })

    it('omits Authorization header when unauthenticated — course detail is public', async () => {
      mockFetch({ code: 'CSCI 1300', title: 'CS 1', credits: '3', dept: 'CSCI', sections: [] })
      await fetchCourse('CSCI 1300')
      const [, requestInit] = getLastFetchCall()
      expect((requestInit?.headers as Record<string, string>)['Authorization']).toBeUndefined()
    })
  })
})
