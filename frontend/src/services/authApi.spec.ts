import { describe, it, expect, vi, beforeEach } from 'vitest'
import { register, fetchPrograms, fetchProgramRequirements, updateCompletedCourses } from '@/services/authApi'
import type { CompletedCoursePayload } from '@/types/index'

function mockFetch(body: unknown, status = 200): void {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(body), { status }),
  )
}

beforeEach(() => vi.restoreAllMocks())

describe('authApi', () => {
  describe('register', () => {
    it('POSTs to /api/auth/register and returns token + user_id', async () => {
      mockFetch({ token: 'abc123', user_id: 42 })
      const result = await register({ email: 'a@b.com', password: 'secure-pass-12', name: 'Alice' })
      const call = vi.mocked(globalThis.fetch).mock.calls[0]
      expect(call[0]).toBe('/api/auth/register')
      expect((call[1] as RequestInit).method).toBe('POST')
      const body = JSON.parse((call[1] as RequestInit).body as string)
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
      const call = vi.mocked(globalThis.fetch).mock.calls[0]
      expect(call[0]).toBe('/api/programs')
      expect((call[1] as RequestInit).headers as Record<string, string>).toMatchObject({
        Authorization: 'Bearer my-token',
      })
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe(1)
    })
  })

  describe('fetchProgramRequirements', () => {
    it('GETs /api/programs/7/requirements with Authorization header', async () => {
      mockFetch({ program: { id: 7, name: 'CS BS', type: 'major' }, requirements: [] })
      await fetchProgramRequirements(7, 'tok')
      const call = vi.mocked(globalThis.fetch).mock.calls[0]
      expect(call[0]).toBe('/api/programs/7/requirements')
      expect((call[1] as RequestInit).headers as Record<string, string>).toMatchObject({
        Authorization: 'Bearer tok',
      })
    })
  })

  describe('updateCompletedCourses', () => {
    it('PUTs /api/students/me/completed-courses with auth header and body', async () => {
      mockFetch({ completed_courses: [] })
      const courses: CompletedCoursePayload[] = [{ course_code: 'CSCI1300', grade: 'A' }]
      await updateCompletedCourses(courses, 'tok')
      const call = vi.mocked(globalThis.fetch).mock.calls[0]
      expect(call[0]).toBe('/api/students/me/completed-courses')
      expect((call[1] as RequestInit).method).toBe('PUT')
      expect((call[1] as RequestInit).headers as Record<string, string>).toMatchObject({
        Authorization: 'Bearer tok',
      })
      const body = JSON.parse((call[1] as RequestInit).body as string)
      expect(body).toEqual([{ course_code: 'CSCI1300', grade: 'A' }])
    })
  })
})
