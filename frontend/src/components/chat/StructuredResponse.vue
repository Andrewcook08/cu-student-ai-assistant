<script setup lang="ts">
import type { CourseCard } from '@/types/index'

defineProps<{
  cards: CourseCard[]
}>()
</script>

<template>
  <div class="structured-response">
    <div v-for="card in cards" :key="card.code" class="course-card">
      <div class="course-card__header">
        <span class="course-card__code">{{ card.code }}</span>
        <span v-if="card.status" :class="['status-chip', card.status.toLowerCase()]">
          {{ card.status }}
        </span>
      </div>
      <div class="course-card__title">{{ card.title }}</div>
      <div class="course-card__meta">
        <span>{{ card.credits }} credits</span>
        <span v-if="card.instruction_mode"> &middot; {{ card.instruction_mode }}</span>
      </div>
      <div v-if="card.description" class="course-card__description">
        {{ card.description }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.structured-response {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}
.course-card {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 13px;
}
.course-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.course-card__code {
  font-weight: 700;
  color: #0277BD;
  font-size: 12px;
  letter-spacing: 0.3px;
}
.course-card__title {
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
  line-height: 1.3;
}
.course-card__meta {
  font-size: 11px;
  color: #888;
  margin-bottom: 4px;
}
.course-card__description {
  font-size: 12px;
  color: #555;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
