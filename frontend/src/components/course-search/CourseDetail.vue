<script setup lang="ts">
import type { Course } from '@/types/index'

defineProps<{
  course: Course
}>()
</script>

<template>
  <tr class="course-detail-row">
    <td colspan="5">
      <div class="course-detail">
        <div class="course-detail__section">
          <h4>Description</h4>
          <p>{{ course.description || 'No description available.' }}</p>
        </div>
        <div v-if="course.prerequisites_raw && course.prerequisites_raw !== 'None'" class="course-detail__section">
          <h4>Prerequisites</h4>
          <p>{{ course.prerequisites_raw }}</p>
        </div>
        <div v-if="course.sections && course.sections.length > 0" class="course-detail__section">
          <h4>Sections</h4>
          <table class="sections-table">
            <thead>
              <tr>
                <th>CRN</th>
                <th>Meets</th>
                <th>Instructor</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="section in course.sections" :key="section.crn">
                <td>{{ section.crn }}</td>
                <td>{{ section.meets || '—' }}</td>
                <td>{{ section.instructor || '—' }}</td>
                <td>
                  <span :class="['status-chip', (section.status || 'unknown').toLowerCase()]">
                    {{ section.status }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </td>
  </tr>
</template>

<style scoped>
.course-detail-row td {
  padding: 0;
  background: #fff;
}
.course-detail {
  padding: 16px 20px;
  border-top: 1px solid #ddd;
  border-bottom: 1px solid #eee;
}
.course-detail__section {
  margin-bottom: 12px;
}
.course-detail__section:last-child {
  margin-bottom: 0;
}
.course-detail__section h4 {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: #555;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.course-detail__section p {
  font-size: 13px;
  color: #333;
  line-height: 1.5;
}
.sections-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.sections-table th {
  text-align: left;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 700;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: #f5f5f5;
  border-bottom: 1px solid #ddd;
}
.sections-table td {
  padding: 6px 10px;
  border-bottom: 1px solid #eee;
  color: #333;
}
</style>
