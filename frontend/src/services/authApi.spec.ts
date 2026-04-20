import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/authStore'
import {
  register,
  login,
  fetchPrograms,
  fetchProgramRequirements,
  updateProgram,
  updateCompletedCourses,
} from '@/services/authApi'
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

beforeEach(() => {
  vi.restoreAllMocks()
  setActivePinia(createPinia())
  sessionStorage.clear()
})

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

  describe('login', () => {
    it('POSTs to /api/auth/login and returns the full backend response shape', async () => {
      const backendResp = {
        access_token: 'jwt-tok',
        token_type: 'bearer',
        expires_in: 3600,
        user_id: 42,
        name: 'Alice',
      }
      mockFetch(backendResp)
      const result = await login('a@b.com', 'p4ssword')
      const [url, requestInit] = getLastFetchCall()
      expect(url).toBe('/api/auth/login')
      expect(requestInit?.method).toBe('POST')
      const body = JSON.parse(String(requestInit?.body))
      expect(body).toEqual({ email: 'a@b.com', password: 'p4ssword' })
      expect(result).toEqual(backendResp)
    })

    it('throws with server detail message on 401', async () => {
      mockFetch({ detail: 'Invalid credentials' }, 401)
      await expect(login('a@b.com', 'wrong')).rejects.toThrow('Invalid credentials')
    })

    it('falls back to friendly message when detail is missing', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 500 }))
      await expect(login('a@b.com', 'p')).rejects.toThrow(/something went wrong/i)
    })

    it('returns friendly 401 copy when detail is missing', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 401 }))
      await expect(login('a@b.com', 'p')).rejects.toThrow('Invalid email or password.')
    })
  })

  describe('fetchPrograms', () => {
    it('GETs /api/programs with Authorization header when authenticated', async () => {
      const store = useAuthStore()
      store.setAuth('my-token', 1, 'Alice')
      mockFetch([{ id: 1, name: 'CS BS', type: 'major', total_credits: 120 }])
      const result = await fetchPrograms()
      const [url, requestInit] = getLastFetchCall()
      expect(url).toBe('/api/programs')
      expect(requestInit?.headers).toMatchObject({
        Authorization: 'Bearer my-token',
      })
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe(1)
    })

    it('GETs /api/programs without Authorization header when unauthenticated', async () => {
      mockFetch([{ id: 1, name: 'CS BS', type: 'major', total_credits: 120 }])
      await fetchPrograms()
      const [, requestInit] = getLastFetchCall()
      expect((requestInit?.headers as Record<string, string>)['Authorization']).toBeUndefined()
    })

    it('surfaces the server detail message on non-ok response', async () => {
      mockFetch({ detail: 'Unauthorized' }, 401)
      await expect(fetchPrograms()).rejects.toThrow('Unauthorized')
    })

    it('falls back to a friendly error when detail is missing', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 503 }))
      await expect(fetchPrograms()).rejects.toThrow(/saving your profile/i)
    })
  })

  describe('fetchProgramRequirements', () => {
    it('GETs /api/programs/7/requirements with Authorization header when authenticated', async () => {
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      mockFetch({ program: { id: 7, name: 'CS BS', type: 'major' }, requirements: [] })
      await fetchProgramRequirements(7)
      const [url, requestInit] = getLastFetchCall()
      expect(url).toBe('/api/programs/7/requirements')
      expect(requestInit?.headers).toMatchObject({
        Authorization: 'Bearer tok',
      })
    })

    it('GETs /api/programs/{id}/requirements without Authorization header when unauthenticated', async () => {
      mockFetch({ program: { id: 7, name: 'CS BS', type: 'major' }, requirements: [] })
      await fetchProgramRequirements(7)
      const [, requestInit] = getLastFetchCall()
      expect((requestInit?.headers as Record<string, string>)['Authorization']).toBeUndefined()
    })

    it('throws on non-ok response', async () => {
      mockFetch({ detail: 'Not found' }, 404)
      await expect(fetchProgramRequirements(999)).rejects.toThrow('Not found')
    })
  })

  describe('updateProgram', () => {
    it('PUTs /api/students/me/program with Authorization header and program_id body', async () => {
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      mockFetch({ ok: true })
      await updateProgram(7)
      const [url, requestInit] = getLastFetchCall()
      expect(url).toBe('/api/students/me/program')
      expect(requestInit?.method).toBe('PUT')
      expect(requestInit?.headers).toMatchObject({ Authorization: 'Bearer tok' })
      const body = JSON.parse(String(requestInit?.body))
      expect(body).toEqual({ program_id: 7 })
    })

    it('sends program_id: null when called with null', async () => {
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      mockFetch({ ok: true })
      await updateProgram(null)
      const [, requestInit] = getLastFetchCall()
      const body = JSON.parse(String(requestInit?.body))
      expect(body).toEqual({ program_id: null })
    })

    it('throws on non-ok response', async () => {
      mockFetch({ detail: 'Unknown program_id' }, 422)
      await expect(updateProgram(999)).rejects.toThrow('Unknown program_id')
    })
  })

  describe('updateCompletedCourses', () => {
    it('PUTs /api/students/me/completed-courses with auth header and body', async () => {
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      mockFetch({ completed_courses: [] })
      const courses: CompletedCoursePayload[] = [{ course_code: 'CSCI1300', grade: 'A' }]
      await updateCompletedCourses(courses)
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
      await expect(updateCompletedCourses([])).rejects.toThrow('Bad request')
    })
  })
})
