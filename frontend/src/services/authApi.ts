import type {
  AuthRegisterResponse,
  RegisterFormData,
  Program,
  Requirement,
  CompletedCoursePayload,
} from '@/types/index'

const API_BASE = '/api'

function authHeaders(token: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
}

export async function register(data: RegisterFormData): Promise<AuthRegisterResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    const msg = typeof err.detail === 'string' ? err.detail : `Registration failed: ${res.status}`
    throw new Error(msg)
  }
  return res.json()
}

export async function fetchPrograms(token: string): Promise<Program[]> {
  const res = await fetch(`${API_BASE}/programs`, { headers: authHeaders(token) })
  if (!res.ok) throw new Error(`Failed to fetch programs: ${res.status}`)
  return res.json()
}

export async function fetchProgramRequirements(
  programId: number,
  token: string,
): Promise<{ program: Program; requirements: Requirement[] }> {
  const res = await fetch(`${API_BASE}/programs/${programId}/requirements`, {
    headers: authHeaders(token),
  })
  if (!res.ok) throw new Error(`Failed to fetch requirements: ${res.status}`)
  return res.json()
}

export async function updateCompletedCourses(
  courses: CompletedCoursePayload[],
  token: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/students/me/completed-courses`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify(courses),
  })
  if (!res.ok) throw new Error(`Failed to update completed courses: ${res.status}`)
}
