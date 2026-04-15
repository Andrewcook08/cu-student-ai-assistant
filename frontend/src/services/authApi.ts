import type {
  AuthRegisterResponse,
  AuthLoginResponse,
  RegisterFormData,
  Program,
  CompletedCoursePayload,
  ProgramRequirementsResponse,
} from '@/types/index'

const API_BASE = '/api'

function authHeaders(token: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
}

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
  const errorBody: unknown = await response.json().catch(() => null)

  if (
    errorBody !== null &&
    typeof errorBody === 'object' &&
    'detail' in errorBody &&
    typeof errorBody.detail === 'string'
  ) {
    return errorBody.detail
  }

  return `${fallback}: ${response.status}`
}

export async function register(data: RegisterFormData): Promise<AuthRegisterResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    throw new Error(await getErrorMessage(res, 'Registration failed'))
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
    throw new Error(await getErrorMessage(res, 'Login failed'))
  }
  return res.json()
}

export async function fetchPrograms(token: string): Promise<Program[]> {
  const res = await fetch(`${API_BASE}/programs`, { headers: authHeaders(token) })
  if (!res.ok) throw new Error(await getErrorMessage(res, 'Failed to fetch programs'))
  return res.json()
}

export async function fetchProgramRequirements(
  programId: number,
  token: string,
): Promise<ProgramRequirementsResponse> {
  const res = await fetch(`${API_BASE}/programs/${programId}/requirements`, {
    headers: authHeaders(token),
  })
  if (!res.ok) throw new Error(await getErrorMessage(res, 'Failed to fetch requirements'))
  return res.json()
}

export async function updateProgram(programId: number | null, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/students/me/program`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify({ program_id: programId }),
  })
  if (!res.ok) throw new Error(await getErrorMessage(res, 'Failed to update program'))
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
  if (!res.ok) throw new Error(await getErrorMessage(res, 'Failed to update completed courses'))
}
