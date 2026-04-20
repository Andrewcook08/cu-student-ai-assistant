import type {
  AuthRegisterResponse,
  AuthLoginResponse,
  RegisterFormData,
  Program,
  CompletedCoursePayload,
  ProgramRequirementsResponse,
} from '@/types/index'
import { apiFetch } from '@/services/api'
import { extractApiError } from '@/utils/errorMessages'

const API_BASE = '/api'

export async function register(data: RegisterFormData): Promise<AuthRegisterResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'auth'))
  }
  return res.json()
}

export async function login(email: string, password: string): Promise<AuthLoginResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'auth'))
  }
  return res.json()
}

export async function fetchPrograms(): Promise<Program[]> {
  const res = await apiFetch(`${API_BASE}/programs`)
  if (!res.ok) throw new Error(await extractApiError(res, 'profile'))
  return res.json()
}

export async function fetchProgramRequirements(
  programId: number,
): Promise<ProgramRequirementsResponse> {
  const res = await apiFetch(`${API_BASE}/programs/${programId}/requirements`)
  if (!res.ok) throw new Error(await extractApiError(res, 'profile'))
  return res.json()
}

export async function updateProgram(programId: number | null): Promise<void> {
  const res = await apiFetch(`${API_BASE}/students/me/program`, {
    method: 'PUT',
    body: JSON.stringify({ program_id: programId }),
  })
  if (!res.ok) throw new Error(await extractApiError(res, 'profile'))
}

export async function updateCompletedCourses(
  courses: CompletedCoursePayload[],
): Promise<void> {
  const res = await apiFetch(`${API_BASE}/students/me/completed-courses`, {
    method: 'PUT',
    body: JSON.stringify(courses),
  })
  if (!res.ok) throw new Error(await extractApiError(res, 'profile'))
}
