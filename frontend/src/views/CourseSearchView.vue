<script setup lang="ts">
import { ref } from 'vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import FilterBar from '@/components/layout/FilterBar.vue'
import type { FilterValues } from '@/types/index'

const hasSearched = ref(false)
const activeFilters = ref<FilterValues>({ dept: '', level: '', time: '', credits: '' })

function onSearch(filters: FilterValues) {
  activeFilters.value = filters
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
      <div class="empty-space">
        <div class="empty-space__content">
          <p v-if="!hasSearched" style="color: #888; font-size: 14px;">Use the filters on the left to search for classes.</p>
          <p v-else style="color: #555; font-size: 14px;">
            Showing results for:
            <strong>{{ activeFilters.dept || 'All Departments' }}</strong>
            — Course table coming in next PR.
          </p>
        </div>
      </div>
    </main>
    <AppFooter />
  </div>
</template>
