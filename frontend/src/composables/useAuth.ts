import { ref } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import {
  register as apiRegister,
  fetchPrograms as apiFetchPrograms,
  fetchProgramRequirements,
  updateCompletedCourses as apiUpdateCourses,
} from '@/services/authApi'
import type {
  RegisterFormData,
  AuthRegisterResponse,
  Program,
  Requirement,
  CompletedCoursePayload,
} from '@/types/index'

export function useAuth() {
  const store = useAuthStore()
  const loading = ref(false)
  const error = ref<string | null>(null)

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

  async function fetchPrograms(token: string): Promise<Program[]> {
    loading.value = true
    error.value = null
    try {
      return await apiFetchPrograms(token)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load programs'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchRequirements(
    programId: number,
    token: string,
  ): Promise<{ program: Program; requirements: Requirement[] }> {
    loading.value = true
    error.value = null
    try {
      return await fetchProgramRequirements(programId, token)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load requirements'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateCompletedCourses(
    courses: CompletedCoursePayload[],
    token: string,
  ): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await apiUpdateCourses(courses, token)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update courses'
      throw e
    } finally {
      loading.value = false
    }
  }

  return { loading, error, register, fetchPrograms, fetchRequirements, updateCompletedCourses }
}
