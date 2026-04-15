import { describe, it, expect, vi, beforeEach } from 'vitest'
import { register, fetchPrograms, fetchProgramRequirements, updateCompletedCourses } from '@/services/authApi'
import type { CompletedCoursePayload } from '@/types/index'

function mockFetch(body: unknown, status = 200): void {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(body), { status }),
  )
}

function getLastFetchCall(): [RequestInfo | URL, RequestInit | undefined] {
  const lastCall = vi.mocked(globalThis.fetch).mock.calls.at(-1)

  if (!lastCall) {
    throw new Error('Expected fetch to have been called')
  }

  return [lastCall[0], lastCall[1] as RequestInit | undefined]
}

beforeEach(() => vi.restoreAllMocks())

describe('authApi', () => {
  describe('register', () => {
    it('POSTs to /api/auth/register and returns token + user_id', async () => {
      mockFetch({ token: 'abc123', user_id: 42 })
      const result = await register({ email: 'a@b.com', password: 'secure-pass-12', name: 'Alice' })
      const [url, requestInit] = getLastFetchCall()
      expect(url).toBe('/api/auth/register')
      expect(requestInit?.method).toBe('POST')
      const body = JSON.parse(String(requestInit?.body))
      expect(body).toEqual({ email: 'a@b.com', password: 'secure-pass-12', name: 'Alice' })
      expect(result).toEqual({ token: 'abc123', user_id: 42 })
    })

    it('throws with server detail message on 400', async () => {
      mockFetch({ detail: 'Registration failed' }, 400)
      await expect(
        register({ email: 'a@b.com', password: 'secure-pass-12', name: 'Alice' }),
      ).rejects.toThrow('Registration failed')
    })

    it('throws with server detail message on 422', async () => {
      mockFetch({ detail: 'Unknown program_id' }, 422)
      await expect(
        register({ email: 'a@b.com', password: 'secure-pass-12', name: 'Alice' }),
      ).rejects.toThrow('Unknown program_id')
    })
  })

  describe('fetchPrograms', () => {
    it('GETs /api/programs with Authorization header', async () => {
      mockFetch([{ id: 1, name: 'CS BS', type: 'major', total_credits: 120 }])
      const result = await fetchPrograms('my-token')
      const [url, requestInit] = getLastFetchCall()
      expect(url).toBe('/api/programs')
      expect(requestInit?.headers).toMatchObject({
        Authorization: 'Bearer my-token',
      })
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe(1)
    })

    it('surfaces the server detail message on non-ok response', async () => {
      mockFetch({ detail: 'Unauthorized' }, 401)
      await expect(fetchPrograms('bad-tok')).rejects.toThrow('Unauthorized')
    })

    it('falls back to a status-based error when detail is missing', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 503 }))
      await expect(fetchPrograms('bad-tok')).rejects.toThrow('Failed to fetch programs: 503')
    })
  })

  describe('fetchProgramRequirements', () => {
    it('GETs /api/programs/7/requirements with Authorization header', async () => {
      mockFetch({ program: { id: 7, name: 'CS BS', type: 'major' }, requirements: [] })
      await fetchProgramRequirements(7, 'tok')
      const [url, requestInit] = getLastFetchCall()
      expect(url).toBe('/api/programs/7/requirements')
      expect(requestInit?.headers).toMatchObject({
        Authorization: 'Bearer tok',
      })
    })

    it('throws on non-ok response', async () => {
      mockFetch({ detail: 'Not found' }, 404)
      await expect(fetchProgramRequirements(999, 'tok')).rejects.toThrow('Not found')
    })
  })

  describe('updateCompletedCourses', () => {
    it('PUTs /api/students/me/completed-courses with auth header and body', async () => {
      mockFetch({ completed_courses: [] })
      const courses: CompletedCoursePayload[] = [{ course_code: 'CSCI1300', grade: 'A' }]
      await updateCompletedCourses(courses, 'tok')
      const [url, requestInit] = getLastFetchCall()
      expect(url).toBe('/api/students/me/completed-courses')
      expect(requestInit?.method).toBe('PUT')
      expect(requestInit?.headers).toMatchObject({
        Authorization: 'Bearer tok',
      })
      const body = JSON.parse(String(requestInit?.body))
      expect(body).toEqual([{ course_code: 'CSCI1300', grade: 'A' }])
    })

    it('throws on non-ok response', async () => {
      mockFetch({ detail: 'Bad request' }, 400)
      await expect(updateCompletedCourses([], 'tok')).rejects.toThrow('Bad request')
    })
  })
})
