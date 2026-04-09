import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Course, FilterValues } from '@/types/index'

export const useCourseStore = defineStore('courses', () => {
  const courses = ref<Course[]>([])
  const selectedCourse = ref<Course | null>(null)
  const total = ref(0)
  const offset = ref(0)
  const limit = ref(50)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const activeFilters = ref<FilterValues>({ dept: '', level: '', credits: '' })
  const expandedCode = ref<string | null>(null)
  const hasSearched = ref(false)

  function setCourses(items: Course[], newTotal: number) {
    courses.value = items
    total.value = newTotal
  }

  function selectCourse(course: Course | null) {
    selectedCourse.value = course
  }

  function setLoading(v: boolean) {
    loading.value = v
  }

  function setError(msg: string | null) {
    error.value = msg
  }

  function setActiveFilters(f: FilterValues) {
    activeFilters.value = { ...f }
  }

  function toggleExpanded(code: string) {
    expandedCode.value = expandedCode.value === code ? null : code
  }

  function setHasSearched(v: boolean) {
    hasSearched.value = v
  }

  function resetPage() {
    offset.value = 0
  }

  function advancePage(direction: 1 | -1) {
    offset.value = Math.max(0, offset.value + limit.value * direction)
  }

  return {
    courses,
    selectedCourse,
    total,
    offset,
    limit,
    loading,
    error,
    activeFilters,
    expandedCode,
    hasSearched,
    setCourses,
    selectCourse,
    setLoading,
    setError,
    setActiveFilters,
    toggleExpanded,
    setHasSearched,
    resetPage,
    advancePage,
  }
})
