<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import FilterBar from '@/components/layout/FilterBar.vue'
import WelcomePane from '@/components/course-search/WelcomePane.vue'
import CourseTable from '@/components/course-search/CourseTable.vue'
import type { FilterValues } from '@/types/index'
import type { CourseFilters } from '@/services/courseApi'
import { useCourses } from '@/composables/useCourses'
import { useCourseStore } from '@/stores/courseStore'

const {
  courses,
  total,
  loading,
  error,
  offset,
  fetch: fetchCourses,
  nextPage,
  prevPage,
  resetPage,
} = useCourses()

const store = useCourseStore()
const { hasSearched, activeFilters } = storeToRefs(store)

function toApiFilters(filters: FilterValues): CourseFilters {
  return {
    dept: filters.dept || undefined,
    level: filters.level || undefined,
    credits: filters.credits || undefined,
  }
}

async function onSearch(filters: FilterValues) {
  store.setActiveFilters(filters)
  store.setHasSearched(true)
  resetPage()
  await fetchCourses(toApiFilters(filters))
}

async function onNext() {
  await nextPage(toApiFilters(activeFilters.value))
}

async function onPrev() {
  await prevPage(toApiFilters(activeFilters.value))
}

const canPrev = computed(() => offset.value > 0)
const canNext = computed(() => offset.value + courses.value.length < total.value)
const rangeStart = computed(() => (total.value === 0 ? 0 : offset.value + 1))
const rangeEnd = computed(() => Math.min(offset.value + courses.value.length, total.value))
</script>

<template>
  <div style="display: flex; flex-direction: column; min-height: 100vh;">
    <AppHeader />
    <main class="panels" style="flex: 1;">
      <div class="panel panel--visible">
        <FilterBar @search="onSearch" />
      </div>
      <div class="empty-space" :class="{ 'empty-space--searching': hasSearched }">
        <WelcomePane v-if="!hasSearched" />
        <template v-else>
          <!-- Loading state -->
          <div v-if="loading" class="search-status">
            <span class="search-status__text">Loading courses...</span>
          </div>
          <!-- Error toast -->
          <div v-else-if="error" class="search-status search-status--error" role="alert">
            <span class="search-status__text">{{ error }}</span>
          </div>
          <!-- Results -->
          <CourseTable :courses="courses" />
          <!-- Pagination -->
          <div v-if="total > 0" class="pagination">
            <span class="pagination__info">
              Showing {{ rangeStart }}–{{ rangeEnd }} of {{ total }}
            </span>
            <div class="pagination__controls">
              <button
                type="button"
                class="pagination__btn"
                :disabled="!canPrev || loading"
                @click="onPrev"
              >
                Prev
              </button>
              <button
                type="button"
                class="pagination__btn"
                :disabled="!canNext || loading"
                @click="onNext"
              >
                Next
              </button>
            </div>
          </div>
        </template>
      </div>
    </main>
    <AppFooter />
  </div>
</template>

<style scoped>
.empty-space--searching {
  align-items: flex-start;
  justify-content: flex-start;
  padding: 0;
  overflow-y: auto;
}
.search-status {
  padding: 16px 20px;
  font-size: 13px;
  color: #555;
  background: #f9f9f9;
  border-bottom: 1px solid #eee;
}
.search-status--error {
  background: #fff3e0;
  color: #e65100;
}
.search-status__text {
  font-style: italic;
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 20px;
  font-size: 12px;
  color: #555;
  border-top: 1px solid #eee;
  background: #fafafa;
}
.pagination__controls {
  display: flex;
  gap: 8px;
}
.pagination__btn {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #333;
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 3px;
  cursor: pointer;
}
.pagination__btn:hover:not(:disabled) {
  background: #f0f0f0;
}
.pagination__btn:disabled {
  color: #bbb;
  background: #f5f5f5;
  cursor: not-allowed;
}
</style>
