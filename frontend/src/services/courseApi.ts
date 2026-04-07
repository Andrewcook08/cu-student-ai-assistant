import type { Course, PaginatedResponse } from '@/types/index'

const API_BASE = '/api'

export interface CourseFilters {
  dept?: string
  level?: string
  instruction_mode?: string
  status?: string
  credits?: string
  q?: string
  offset?: number
  limit?: number
}

export async function fetchCourses(
  filters: CourseFilters = {},
): Promise<PaginatedResponse<Course>> {
  const params = new URLSearchParams()
  if (filters.dept) params.set('dept', filters.dept)
  if (filters.level) params.set('level', filters.level)
  if (filters.instruction_mode) params.set('instruction_mode', filters.instruction_mode)
  if (filters.status) params.set('status', filters.status)
  if (filters.credits) params.set('credits', filters.credits)
  if (filters.q) params.set('q', filters.q)
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))

  const res = await fetch(`${API_BASE}/courses?${params.toString()}`)
  if (!res.ok) throw new Error(`Failed to fetch courses: ${res.status}`)
  return res.json()
}

export async function fetchCourse(code: string): Promise<Course> {
  const res = await fetch(`${API_BASE}/courses/${encodeURIComponent(code)}`)
  if (res.status === 404) throw new Error(`Course '${code}' not found`)
  if (!res.ok) throw new Error(`Failed to fetch course: ${res.status}`)
  return res.json()
}
