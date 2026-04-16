import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAuth } from '@/composables/useAuth'
import { useAuthStore } from '@/stores/authStore'
import * as authApi from '@/services/authApi'

beforeEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

// payload = {"sub":1,"exp":9999999999}
const validJwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6OTk5OTk5OTk5OX0.sig'

describe('useAuth', () => {
  describe('login', () => {
    it('calls authApi.login, stores token in authStore, and resolves', async () => {
      vi.spyOn(authApi, 'login').mockResolvedValue({ token: validJwt })
      const { login, loading, error } = useAuth()
      await login({ email: 'a@b.com', password: 'secure-pass-12' })
      expect(authApi.login).toHaveBeenCalledWith('a@b.com', 'secure-pass-12')
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(true)
      expect(store.token).toBe(validJwt)
      expect(store.userId).toBe(1)
      expect(store.userName).toBe('a@b.com')
      expect(loading.value).toBe(false)
      expect(error.value).toBeNull()
      expect(sessionStorage.getItem('token')).toBe(validJwt)
    })

    it('sets error.value and rethrows on authApi.login failure', async () => {
      vi.spyOn(authApi, 'login').mockRejectedValue(new Error('Invalid credentials'))
      const { login, error } = useAuth()
      await expect(
        login({ email: 'a@b.com', password: 'wrong' }),
      ).rejects.toThrow('Invalid credentials')
      expect(error.value).toBe('Invalid credentials')
    })

    it('throws and sets error when token sub cannot be parsed', async () => {
      vi.spyOn(authApi, 'login').mockResolvedValue({ token: 'bad.token.here' })
      const { login, error } = useAuth()
      await expect(login({ email: 'a@b.com', password: 'p' })).rejects.toThrow(
        'Invalid token received from server',
      )
      expect(error.value).toBe('Invalid token received from server')
    })
  })

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
      expect(sessionStorage.getItem('token')).toBe('tok')
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
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      const { fetchPrograms, loading } = useAuth()
      const programs = await fetchPrograms()
      expect(programs).toHaveLength(1)
      expect(loading.value).toBe(false)
    })

    it('sets error.value and rethrows on failure', async () => {
      vi.spyOn(authApi, 'fetchPrograms').mockRejectedValue(new Error('Failed to load programs'))
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      const { fetchPrograms, error } = useAuth()
      await expect(fetchPrograms()).rejects.toThrow('Failed to load programs')
      expect(error.value).toBe('Failed to load programs')
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
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      const { fetchRequirements } = useAuth()
      const result = await fetchRequirements(1)
      expect(result.requirements).toHaveLength(1)
      expect(result.requirements[0].course_code).toBe('CSCI1300')
    })

    it('sets error.value and rethrows on failure', async () => {
      vi.spyOn(authApi, 'fetchProgramRequirements').mockRejectedValue(new Error('Failed to load requirements'))
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      const { fetchRequirements, error } = useAuth()
      await expect(fetchRequirements(99)).rejects.toThrow('Failed to load requirements')
      expect(error.value).toBe('Failed to load requirements')
    })
  })

  describe('updateCompletedCourses', () => {
    it('delegates to authApi.updateCompletedCourses', async () => {
      vi.spyOn(authApi, 'updateCompletedCourses').mockResolvedValue(undefined)
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      const { updateCompletedCourses } = useAuth()
      await updateCompletedCourses([{ course_code: 'CSCI1300', grade: 'A' }])
      expect(authApi.updateCompletedCourses).toHaveBeenCalledWith(
        [{ course_code: 'CSCI1300', grade: 'A' }],
      )
    })

    it('sets error.value and rethrows on failure', async () => {
      vi.spyOn(authApi, 'updateCompletedCourses').mockRejectedValue(new Error('Failed to update courses'))
      const store = useAuthStore()
      store.setAuth('tok', 1, 'Alice')
      const { updateCompletedCourses, error } = useAuth()
      await expect(
        updateCompletedCourses([{ course_code: 'CSCI1300' }]),
      ).rejects.toThrow('Failed to update courses')
      expect(error.value).toBe('Failed to update courses')
    })
  })
})
