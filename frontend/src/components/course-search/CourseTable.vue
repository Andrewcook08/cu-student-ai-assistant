<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Course } from '@/types/index'
import type { FilterValues } from '@/types/index'
import CourseRow from './CourseRow.vue'

const props = defineProps<{
  courses: Course[]
  filters: FilterValues
}>()

const expandedCode = ref<string | null>(null)

function toggleExpand(code: string) {
  expandedCode.value = expandedCode.value === code ? null : code
}

const filteredCourses = computed(() => {
  return props.courses.filter((c) => {
    if (props.filters.dept && c.dept !== props.filters.dept) return false
    if (props.filters.credits && c.credits !== props.filters.credits) return false
    if (props.filters.level) {
      const num = parseInt(c.code.split(' ')[1] ?? '0', 10)
      if (props.filters.level === 'undergrad-lower' && (num < 1000 || num > 2999)) return false
      if (props.filters.level === 'undergrad-upper' && (num < 3000 || num > 4999)) return false
      if (props.filters.level === 'graduate' && num < 5000) return false
    }
    return true
  })
})
</script>

<template>
  <div class="course-table-wrapper">
    <div v-if="filteredCourses.length === 0" class="empty-state">
      No courses match your filters. Try adjusting your search criteria.
    </div>
    <table v-else class="course-table">
      <thead>
        <tr>
          <th>Code</th>
          <th>Title</th>
          <th>Credits</th>
          <th>Mode</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="course in filteredCourses" :key="course.code">
          <CourseRow
            :course="course"
            :is-expanded="expandedCode === course.code"
            @select="toggleExpand"
          />
        </template>
      </tbody>
    </table>
    <div class="course-table-footer">
      Showing {{ filteredCourses.length }} of {{ courses.length }} courses
    </div>
  </div>
</template>

<style scoped>
.course-table-wrapper {
  width: 100%;
  overflow-x: auto;
}
.course-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
}
.course-table thead th {
  text-align: left;
  padding: 10px 12px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #555;
  background: #f5f5f5;
  border-bottom: 2px solid #ddd;
  position: sticky;
  top: 0;
}
.empty-state {
  padding: 40px;
  text-align: center;
  color: #888;
  font-size: 14px;
}
.course-table-footer {
  padding: 8px 12px;
  font-size: 12px;
  color: #888;
  border-top: 1px solid #eee;
  background: #fafafa;
}
</style>
