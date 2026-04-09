<script setup lang="ts">
import { storeToRefs } from 'pinia'
import type { Course } from '@/types/index'
import CourseRow from './CourseRow.vue'
import { useCourseStore } from '@/stores/courseStore'

const props = defineProps<{
  courses: Course[]
}>()

const store = useCourseStore()
const { expandedCode } = storeToRefs(store)

function toggleExpand(code: string) {
  store.toggleExpanded(code)
}
</script>

<template>
  <div class="course-table-wrapper">
    <div v-if="props.courses.length === 0" class="empty-state">
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
        <template v-for="course in props.courses" :key="course.code">
          <CourseRow
            :course="course"
            :is-expanded="expandedCode === course.code"
            @select="toggleExpand"
          />
        </template>
      </tbody>
    </table>
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
</style>
