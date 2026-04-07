<script setup lang="ts">
import { ref } from 'vue'
import type { FilterValues } from '@/types/index'

const emit = defineEmits<{
  search: [filters: FilterValues]
}>()

const dept = ref('')
const level = ref('')
const time = ref('')
const credits = ref('')

function handleSearch() {
  emit('search', {
    dept: dept.value,
    level: level.value,
    time: time.value,
    credits: credits.value,
  })
}
</script>

<template>
  <div class="panel__head">
    <h2>Search Classes</h2>
  </div>
  <div class="panel__body">
    <form @submit.prevent="handleSearch">
      <div class="section">
        <span class="section__title">Search Classes</span>
        <div class="section__content">
          <div class="form-group">
            <label for="filter-dept">Department</label>
            <select id="filter-dept" v-model="dept" class="form-control">
              <option value="">All Departments</option>
              <option value="CSCI">CSCI — Computer Science</option>
              <option value="MATH">MATH — Mathematics</option>
              <option value="PHYS">PHYS — Physics</option>
              <option value="CHEM">CHEM — Chemistry</option>
              <option value="BIOL">BIOL — Biology</option>
              <option value="ENGL">ENGL — English</option>
              <option value="HIST">HIST — History</option>
              <option value="PSYC">PSYC — Psychology</option>
              <option value="ECON">ECON — Economics</option>
              <option value="BUSN">BUSN — Business</option>
              <option value="ASTR">ASTR — Astronomy</option>
              <option value="ENVS">ENVS — Environmental Studies</option>
            </select>
          </div>
          <div class="form-group">
            <label for="filter-level">Level</label>
            <select id="filter-level" v-model="level" class="form-control">
              <option value="">All Levels</option>
              <option value="undergrad-lower">Undergrad Lower (1000–2999)</option>
              <option value="undergrad-upper">Undergrad Upper (3000–4999)</option>
              <option value="graduate">Graduate (5000+)</option>
              <option value="law">Law</option>
              <option value="non-credit">Non-Credit</option>
            </select>
          </div>
          <div class="form-group">
            <label for="filter-time">Time</label>
            <input
              id="filter-time"
              v-model="time"
              type="text"
              class="form-control"
              placeholder="e.g. MWF 9:00–9:50"
            />
          </div>
          <div class="form-group">
            <label for="filter-credits">Credit Hours</label>
            <select id="filter-credits" v-model="credits" class="form-control">
              <option value="">Any Credits</option>
              <option value="1">1 Credit</option>
              <option value="2">2 Credits</option>
              <option value="3">3 Credits</option>
              <option value="4">4 Credits</option>
              <option value="5">5+ Credits</option>
            </select>
          </div>
          <div class="form-group">
            <button type="submit" class="btn btn--full">SEARCH CLASSES</button>
          </div>
        </div>
      </div>
    </form>
  </div>
</template>
