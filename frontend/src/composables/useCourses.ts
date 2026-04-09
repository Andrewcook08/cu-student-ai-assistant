import { storeToRefs } from 'pinia'
import { fetchCourses, type CourseFilters } from '@/services/courseApi'
import { useCourseStore } from '@/stores/courseStore'

export function useCourses() {
  const store = useCourseStore()
  const { courses, total, loading, error, offset, limit } = storeToRefs(store)

  async function fetch(filters: CourseFilters = {}) {
    store.setLoading(true)
    store.setError(null)
    try {
      const result = await fetchCourses({
        ...filters,
        offset: offset.value,
        limit: limit.value,
      })
      store.setCourses(result.items, result.total)
    } catch (e) {
      store.setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      store.setLoading(false)
    }
  }

  async function nextPage(filters: CourseFilters = {}) {
    if (offset.value + limit.value < total.value) {
      store.advancePage(1)
      await fetch(filters)
    }
  }

  async function prevPage(filters: CourseFilters = {}) {
    if (offset.value > 0) {
      store.advancePage(-1)
      await fetch(filters)
    }
  }

  function resetPage() {
    store.resetPage()
  }

  return { courses, total, loading, error, offset, limit, fetch, nextPage, prevPage, resetPage }
}
