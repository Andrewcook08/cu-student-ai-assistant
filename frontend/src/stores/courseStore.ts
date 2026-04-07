import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Course } from '@/types/index'

export const useCourseStore = defineStore('courses', () => {
  const courses = ref<Course[]>([])
  const selectedCourse = ref<Course | null>(null)
  const total = ref(0)
  const offset = ref(0)
  const limit = ref(50)

  function setCourses(items: Course[], newTotal: number) {
    courses.value = items
    total.value = newTotal
  }

  function selectCourse(course: Course | null) {
    selectedCourse.value = course
  }

  return { courses, selectedCourse, total, offset, limit, setCourses, selectCourse }
})
