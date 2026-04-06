import { ref } from 'vue'
import type { Course } from '@/types/index'
import { fetchCourses, type CourseFilters } from '@/services/courseApi'

export function useCourses() {
  const courses = ref<Course[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const offset = ref(0)
  const limit = ref(50)

  async function fetch(filters: CourseFilters = {}) {
    loading.value = true
    error.value = null
    try {
      const result = await fetchCourses({
        ...filters,
        offset: offset.value,
        limit: limit.value,
      })
      courses.value = result.items
      total.value = result.total
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  async function nextPage(filters: CourseFilters = {}) {
    if (offset.value + limit.value < total.value) {
      offset.value += limit.value
      await fetch(filters)
    }
  }

  async function prevPage(filters: CourseFilters = {}) {
    if (offset.value > 0) {
      offset.value = Math.max(0, offset.value - limit.value)
      await fetch(filters)
    }
  }

  function resetPage() {
    offset.value = 0
  }

  return { courses, total, loading, error, offset, limit, fetch, nextPage, prevPage, resetPage }
}
