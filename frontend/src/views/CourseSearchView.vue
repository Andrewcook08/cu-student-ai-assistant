<script setup lang="ts">
import { ref } from 'vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import FilterBar from '@/components/layout/FilterBar.vue'
import WelcomePane from '@/components/course-search/WelcomePane.vue'
import CourseTable from '@/components/course-search/CourseTable.vue'
import type { FilterValues } from '@/types/index'
import { mockCourses } from '@/mocks/courses'

const hasSearched = ref(false)
const activeFilters = ref<FilterValues>({ dept: '', level: '', time: '', credits: '' })

function onSearch(filters: FilterValues) {
  activeFilters.value = { ...filters }
  hasSearched.value = true
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
        <CourseTable
          v-else
          :courses="mockCourses"
          :filters="activeFilters"
        />
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
</style>
