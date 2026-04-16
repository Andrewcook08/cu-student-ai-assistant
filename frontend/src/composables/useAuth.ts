import { ref } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import {
  register as apiRegister,
  login as apiLogin,
  fetchPrograms as apiFetchPrograms,
  fetchProgramRequirements,
  updateProgram as apiUpdateProgram,
  updateCompletedCourses as apiUpdateCourses,
} from '@/services/authApi'
import type {
  LoginFormData,
  RegisterFormData,
  AuthRegisterResponse,
  Program,
  CompletedCoursePayload,
  ProgramRequirementsResponse,
} from '@/types/index'

export function useAuth() {
  const store = useAuthStore()
  const loading = ref(false)
  const error = ref<string | null>(null)

  function requireToken(): string {
    if (!store.token) {
      throw new Error('You must be signed in to continue')
    }
    return store.token
  }

  async function login(data: LoginFormData): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const result = await apiLogin(data.email, data.password)
      const userId = store.parseTokenSub(result.token)
      if (!userId) throw new Error('Invalid token received from server')
      store.setAuth(result.token, userId, data.email)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Login failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function register(data: RegisterFormData): Promise<AuthRegisterResponse> {
    loading.value = true
    error.value = null
    try {
      const result = await apiRegister(data)
      store.setAuth(result.token, result.user_id, data.name)
      return result
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Registration failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchPrograms(): Promise<Program[]> {
    loading.value = true
    error.value = null
    try {
      requireToken()
      return await apiFetchPrograms()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load programs'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchRequirements(programId: number): Promise<ProgramRequirementsResponse> {
    loading.value = true
    error.value = null
    try {
      requireToken()
      return await fetchProgramRequirements(programId)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load requirements'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateProgram(programId: number | null): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await apiUpdateProgram(programId, requireToken())
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update program'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateCompletedCourses(courses: CompletedCoursePayload[]): Promise<void> {
    loading.value = true
    error.value = null
    try {
      requireToken()
      await apiUpdateCourses(courses)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update courses'
      throw e
    } finally {
      loading.value = false
    }
  }

  return { loading, error, login, register, fetchPrograms, fetchRequirements, updateProgram, updateCompletedCourses }
}
