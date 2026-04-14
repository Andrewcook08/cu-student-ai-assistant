<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useAuth } from '@/composables/useAuth'
import type { CompletedCoursePayload, Program, Requirement } from '@/types/index'

const emit = defineEmits<{ close: [] }>()

const { loading, error, register, fetchPrograms, fetchRequirements, updateCompletedCourses } =
  useAuth()

// Step 1 fields
const email = ref('')
const password = ref('')
const name = ref('')

// Step tracking
const step = ref<1 | 2>(1)
let registeredToken = ''

// Step 2 state
const programs = ref<Program[]>([])
const selectedProgramId = ref<number | null>(null)
const requirements = ref<Requirement[]>([])
// checkedCourses: map of course_code → grade string
const checkedCourses = ref<Record<string, string>>({})

// Password strength (client-side only — server validation is authoritative)
interface PasswordStrength {
  label: string
  colorClass: string
}

function computePasswordStrength(pw: string): PasswordStrength {
  if (!pw) return { label: '', colorClass: '' }
  const hasUpper = /[A-Z]/.test(pw)
  const hasLower = /[a-z]/.test(pw)
  const hasDigit = /[0-9]/.test(pw)
  const hasSpecial = /[^A-Za-z0-9]/.test(pw)
  const types = [hasUpper, hasLower, hasDigit, hasSpecial].filter(Boolean).length
  if (pw.length < 8) return { label: 'Too short', colorClass: 'strength--weak' }
  if (pw.length < 12) return { label: 'Weak', colorClass: 'strength--weak' }
  if (types <= 2) return { label: 'Fair', colorClass: 'strength--fair' }
  if (types === 3) return { label: 'Strong', colorClass: 'strength--strong' }
  return { label: 'Very strong', colorClass: 'strength--strong' }
}

const strength = computed(() => computePasswordStrength(password.value))

// Load requirements when program selection changes
watch(selectedProgramId, async (id) => {
  if (id === null) {
    requirements.value = []
    return
  }
  try {
    const result = await fetchRequirements(id, registeredToken)
    requirements.value = result.requirements.filter((r) => r.course_code)
  } catch {
    // error.value is already set by useAuth; the error-msg paragraph will render
    requirements.value = []
  }
})

function toggleCourse(code: string) {
  if (code in checkedCourses.value) {
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete checkedCourses.value[code]
  } else {
    checkedCourses.value[code] = ''
  }
}

async function submitStep1() {
  try {
    const result = await register({
      email: email.value,
      password: password.value,
      name: name.value,
    })
    registeredToken = result.token
    programs.value = await fetchPrograms(result.token)
    step.value = 2
  } catch {
    // error.value is already set by useAuth for whichever call failed
  }
}

async function submitStep2() {
  const courses: CompletedCoursePayload[] = Object.entries(checkedCourses.value).map(
    ([code, grade]) => ({ course_code: code, ...(grade ? { grade } : {}) }),
  )
  if (courses.length > 0) {
    await updateCompletedCourses(courses, registeredToken)
  }
  emit('close')
}
</script>

<template>
  <div class="modal-backdrop" role="dialog" aria-modal="true" @click.self="emit('close')">
    <div class="modal-box">

      <!-- Step 1: Credentials -->
      <template v-if="step === 1">
        <h2 class="modal-title">Create Account</h2>
        <form @submit.prevent="submitStep1" novalidate>
          <div class="form-group">
            <label for="reg-name">Full Name</label>
            <input
              id="reg-name"
              v-model="name"
              name="name"
              type="text"
              class="form-control"
              autocomplete="name"
              required
              placeholder="Jane Smith"
            />
          </div>
          <div class="form-group">
            <label for="reg-email">Email</label>
            <input
              id="reg-email"
              v-model="email"
              type="email"
              class="form-control"
              autocomplete="email"
              required
              placeholder="jane@colorado.edu"
            />
          </div>
          <div class="form-group">
            <label for="reg-password">Password</label>
            <input
              id="reg-password"
              v-model="password"
              type="password"
              class="form-control"
              autocomplete="new-password"
              required
              placeholder="12+ characters"
            />
            <div
              v-if="password"
              data-testid="password-strength"
              class="strength-bar"
              :class="strength.colorClass"
            >
              {{ strength.label }}
            </div>
            <p class="field-hint">Minimum 12 characters. Server validates final strength.</p>
          </div>

          <p v-if="error" data-testid="error-msg" class="error-text">{{ error }}</p>

          <div class="modal-actions">
            <button
              type="button"
              data-testid="cancel-btn"
              class="btn btn--secondary"
              @click="emit('close')"
            >
              Cancel
            </button>
            <button type="submit" class="btn btn--full" :disabled="loading">
              {{ loading ? 'Creating\u2026' : 'Create Account' }}
            </button>
          </div>
        </form>
      </template>

      <!-- Step 2: Program + completed courses -->
      <template v-else>
        <h2 class="modal-title">Complete Your Profile</h2>

        <div class="form-group">
          <label for="reg-program">Program (optional)</label>
          <select
            id="reg-program"
            v-model="selectedProgramId"
            name="program"
            class="form-control"
          >
            <option :value="null">— Select your program —</option>
            <option v-for="p in programs" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>

        <div v-if="requirements.length > 0" class="courses-section">
          <p class="section-label">Check courses you have already completed</p>
          <ul class="course-list">
            <li v-for="req in requirements" :key="req.id" class="course-item">
              <label class="course-label">
                <input
                  type="checkbox"
                  :value="req.course_code"
                  :checked="req.course_code! in checkedCourses"
                  @change="toggleCourse(req.course_code!)"
                />
                <span class="course-code">{{ req.course_code }}</span>
                <span v-if="req.description" class="course-desc"> — {{ req.description }}</span>
              </label>
              <input
                v-if="req.course_code! in checkedCourses"
                v-model="checkedCourses[req.course_code!]"
                type="text"
                class="grade-input form-control"
                placeholder="Grade (e.g. A)"
                maxlength="3"
              />
            </li>
          </ul>
        </div>

        <p v-if="error" data-testid="error-msg" class="error-text">{{ error }}</p>

        <div class="modal-actions">
          <button
            type="button"
            data-testid="finish-btn"
            class="btn btn--full"
            :disabled="loading"
            @click="submitStep2"
          >
            {{ loading ? 'Saving\u2026' : 'Finish' }}
          </button>
        </div>
      </template>

    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-box {
  background: #fff;
  width: 480px;
  max-width: 95vw;
  max-height: 90vh;
  overflow-y: auto;
  border-radius: 4px;
  padding: 28px 32px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
}

.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: #000;
  margin-bottom: 20px;
  border-bottom: 2px solid #cfb87c;
  padding-bottom: 10px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #555;
  margin-bottom: 4px;
}

.field-hint {
  font-size: 11px;
  color: #888;
  margin-top: 3px;
}

.strength-bar {
  height: 4px;
  border-radius: 2px;
  margin-top: 4px;
  font-size: 11px;
  padding-top: 2px;
}

.strength--weak { background: #e53e3e; color: #e53e3e; }
.strength--fair { background: #d69e2e; color: #d69e2e; }
.strength--strong { background: #38a169; color: #38a169; }

.error-text {
  color: #c53030;
  font-size: 13px;
  margin-bottom: 12px;
  background: #fff5f5;
  border: 1px solid #fc8181;
  padding: 8px 10px;
  border-radius: 3px;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 20px;
}

.btn--secondary {
  background: #fff;
  color: #333;
  border: 1px solid #ccc;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  border-radius: 3px;
}

.btn--secondary:hover { background: #f5f5f5; }

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: #555;
  margin-bottom: 8px;
}

.course-list {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 260px;
  overflow-y: auto;
  border: 1px solid #ddd;
  border-radius: 3px;
}

.course-item {
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
}

.course-item:last-child { border-bottom: none; }

.course-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
}

.course-code { font-weight: 600; color: #000; }
.course-desc { color: #555; }

.grade-input {
  margin-top: 6px;
  width: 120px;
  font-size: 12px;
  padding: 4px 8px;
}
</style>
