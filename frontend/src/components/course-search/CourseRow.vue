<script setup lang="ts">
import type { Course } from '@/types/index'
import CourseDetail from './CourseDetail.vue'

const props = defineProps<{
  course: Course
  isExpanded: boolean
}>()

const emit = defineEmits<{
  select: [code: string]
}>()

function toggle() {
  emit('select', props.course.code)
}
</script>

<template>
  <tr class="course-row" :class="{ 'course-row--expanded': isExpanded }" @click="toggle">
    <td class="course-row__code">{{ course.code }}</td>
    <td class="course-row__title">{{ course.title }}</td>
    <td class="course-row__credits">{{ course.credits }}</td>
    <td class="course-row__mode">{{ course.instruction_mode || '—' }}</td>
    <td class="course-row__status">
      <span :class="['status-chip', (course.status || 'unknown').toLowerCase()]">
        {{ course.status || 'Unknown' }}
      </span>
    </td>
  </tr>
  <CourseDetail v-if="isExpanded" :course="course" />
</template>

<style scoped>
.course-row {
  cursor: pointer;
  border-bottom: 1px solid #eee;
}
.course-row:hover {
  background: #f9f9f9;
}
.course-row--expanded {
  background: #f5f5f5;
}
.course-row td {
  padding: 10px 12px;
  font-size: 13px;
  color: #333;
  vertical-align: middle;
}
.course-row__code {
  font-weight: 600;
  color: #0277BD;
  white-space: nowrap;
}
.course-row__credits {
  text-align: center;
  white-space: nowrap;
}
.course-row__mode {
  font-size: 12px;
  color: #555;
}
</style>
