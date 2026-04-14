import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuth } from '@/composables/useAuth'
import * as authApi from '@/services/authApi'

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('useAuth', () => {
  describe('register', () => {
    it('calls authApi.register, stores token in authStore, and returns response', async () => {
      vi.spyOn(authApi, 'register').mockResolvedValue({ token: 'tok', user_id: 1 })
      const { register, loading, error } = useAuth()
      const result = await register({ email: 'a@b.com', password: 'secure-pass-12', name: 'Alice' })
      expect(authApi.register).toHaveBeenCalledWith({
        email: 'a@b.com',
        password: 'secure-pass-12',
        name: 'Alice',
      })
      expect(result).toEqual({ token: 'tok', user_id: 1 })
      expect(loading.value).toBe(false)
      expect(error.value).toBeNull()
      expect(localStorage.getItem('token')).toBe('tok')
    })

    it('sets error.value and rethrows on authApi.register failure', async () => {
      vi.spyOn(authApi, 'register').mockRejectedValue(new Error('Registration failed'))
      const { register, error } = useAuth()
      await expect(
        register({ email: 'a@b.com', password: 'x', name: 'A' }),
      ).rejects.toThrow('Registration failed')
      expect(error.value).toBe('Registration failed')
    })
  })

  describe('fetchPrograms', () => {
    it('returns programs array and clears loading', async () => {
      vi.spyOn(authApi, 'fetchPrograms').mockResolvedValue([
        { id: 1, name: 'CS BS', type: 'major', total_credits: 120 },
      ])
      const { fetchPrograms, loading } = useAuth()
      const programs = await fetchPrograms('tok')
      expect(programs).toHaveLength(1)
      expect(loading.value).toBe(false)
    })
  })

  describe('fetchRequirements', () => {
    it('returns requirements from authApi.fetchProgramRequirements', async () => {
      const mockResult = {
        program: { id: 1, name: 'CS BS', type: 'major', total_credits: 120 },
        requirements: [
          { id: 1, program_id: 1, sort_order: 1, requirement_type: 'required', course_code: 'CSCI1300' },
        ],
      }
      vi.spyOn(authApi, 'fetchProgramRequirements').mockResolvedValue(mockResult)
      const { fetchRequirements } = useAuth()
      const result = await fetchRequirements(1, 'tok')
      expect(result.requirements).toHaveLength(1)
      expect(result.requirements[0].course_code).toBe('CSCI1300')
    })
  })

  describe('updateCompletedCourses', () => {
    it('delegates to authApi.updateCompletedCourses', async () => {
      vi.spyOn(authApi, 'updateCompletedCourses').mockResolvedValue(undefined)
      const { updateCompletedCourses } = useAuth()
      await updateCompletedCourses([{ course_code: 'CSCI1300', grade: 'A' }], 'tok')
      expect(authApi.updateCompletedCourses).toHaveBeenCalledWith(
        [{ course_code: 'CSCI1300', grade: 'A' }],
        'tok',
      )
    })
  })
})
