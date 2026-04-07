<script setup lang="ts">
import { ref } from 'vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import FilterBar from '@/components/layout/FilterBar.vue'
import WelcomePane from '@/components/course-search/WelcomePane.vue'
import CourseTable from '@/components/course-search/CourseTable.vue'
import type { FilterValues } from '@/types/index'
import { useCourses } from '@/composables/useCourses'

const { courses, total, loading, error, fetch: fetchCourses, resetPage } = useCourses()

const hasSearched = ref(false)
const activeFilters = ref<FilterValues>({ dept: '', level: '', time: '', credits: '' })

async function onSearch(filters: FilterValues) {
  activeFilters.value = { ...filters }
  hasSearched.value = true
  resetPage()
  await fetchCourses({
    dept: filters.dept || undefined,
    credits: filters.credits || undefined,
  })
}
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
          <CourseTable
            :courses="courses"
            :filters="activeFilters"
          />
          <!-- Pagination (real API only) -->
          <div v-if="total > 0" class="pagination">
            <span class="pagination__info">{{ total }} total courses found</span>
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
  padding: 12px 20px;
  font-size: 12px;
  color: #888;
  border-top: 1px solid #eee;
}
</style>
