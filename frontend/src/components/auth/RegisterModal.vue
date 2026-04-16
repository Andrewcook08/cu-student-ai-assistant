<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import { useAuth } from '@/composables/useAuth'
import type { CompletedCoursePayload, Program, Requirement } from '@/types/index'

const emit = defineEmits<{
  close: []
  'switch-to-login': []
}>()

const { loading, error, register, fetchPrograms, fetchRequirements, updateProgram, updateCompletedCourses } =
  useAuth()
const dialogTitleId = 'register-modal-title'

const email = ref('')
const password = ref('')
const name = ref('')
const step = ref<1 | 2>(1)

const programs = ref<Program[]>([])
const selectedProgramId = ref<number | null>(null)
const requirements = ref<Requirement[]>([])
const checkedCourses = ref<Record<string, string>>({})
const nameInput = ref<HTMLInputElement | null>(null)
const programSelect = ref<HTMLSelectElement | null>(null)

interface PasswordStrength {
  label: string
  colorClass: string
}

function computePasswordStrength(value: string): PasswordStrength {
  if (!value) return { label: '', colorClass: '' }

  const hasUpper = /[A-Z]/.test(value)
  const hasLower = /[a-z]/.test(value)
  const hasDigit = /[0-9]/.test(value)
  const hasSpecial = /[^A-Za-z0-9]/.test(value)
  const characterTypes = [hasUpper, hasLower, hasDigit, hasSpecial].filter(Boolean).length

  if (value.length < 8) return { label: 'Too short', colorClass: 'strength--weak' }
  if (value.length < 12) return { label: 'Weak', colorClass: 'strength--weak' }
  if (characterTypes <= 2) return { label: 'Fair', colorClass: 'strength--fair' }
  if (characterTypes === 3) return { label: 'Strong', colorClass: 'strength--strong' }

  return { label: 'Very strong', colorClass: 'strength--strong' }
}

const strength = computed(() => computePasswordStrength(password.value))
const selectableRequirements = computed(() =>
  requirements.value.filter((requirement): requirement is Requirement & { course_code: string } =>
    typeof requirement.course_code === 'string' && requirement.course_code.length > 0,
  ),
)

function focusActiveStepField() {
  void nextTick(() => {
    if (step.value === 1) {
      nameInput.value?.focus()
      return
    }

    programSelect.value?.focus()
  })
}

function closeModal() {
  emit('close')
}

function isChecked(courseCode: string): boolean {
  return courseCode in checkedCourses.value
}

function toggleCourse(courseCode: string) {
  if (isChecked(courseCode)) {
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete checkedCourses.value[courseCode]
    return
  }

  checkedCourses.value[courseCode] = ''
}

function handleEscapeKey(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeModal()
  }
}

watch(selectedProgramId, async (programId) => {
  checkedCourses.value = {}
  if (programId === null) {
    requirements.value = []
    return
  }

  try {
    const result = await fetchRequirements(programId)
    requirements.value = result.requirements
  } catch {
    requirements.value = []
  }
})

watch(step, focusActiveStepField)

onMounted(() => {
  document.addEventListener('keydown', handleEscapeKey)
  focusActiveStepField()
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleEscapeKey)
})

async function submitStep1() {
  try {
    await register({
      email: email.value,
      password: password.value,
      name: name.value,
    })
  } catch {
    // useAuth exposes the error message for the active step
    return
  }

  step.value = 2

  try {
    programs.value = await fetchPrograms()
  } catch {
    // programs list unavailable; user can still finish without selecting one
  }
}

async function submitStep2() {
  const courses: CompletedCoursePayload[] = Object.entries(checkedCourses.value).map(
    ([courseCode, grade]) => ({ course_code: courseCode, ...(grade ? { grade } : {}) }),
  )

  try {
    if (selectedProgramId.value !== null) {
      await updateProgram(selectedProgramId.value)
    }
    if (courses.length > 0) {
      await updateCompletedCourses(courses)
    }
    closeModal()
  } catch {
    // useAuth exposes the error message for the active step
  }
}
</script>

<template>
  <div
    class="modal-backdrop"
    role="dialog"
    :aria-labelledby="dialogTitleId"
    aria-modal="true"
    @click.self="closeModal"
  >
    <div class="modal-box">
      <button
        type="button"
        class="modal__close"
        aria-label="Close"
        data-testid="close-btn"
        @click="closeModal"
      >
        <X :size="18" aria-hidden="true" />
      </button>
      <template v-if="step === 1">
        <h2 :id="dialogTitleId" class="modal-title">Create Account</h2>
        <form @submit.prevent="submitStep1" novalidate>
          <div class="form-group">
            <label for="reg-name">Full Name</label>
            <input
              id="reg-name"
              ref="nameInput"
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

          <p v-if="error" data-testid="error-msg" class="error-text" aria-live="polite">{{ error }}</p>

          <div class="modal-actions">
            <button
              type="button"
              data-testid="cancel-btn"
              class="btn btn--secondary"
              aria-label="Cancel registration"
              @click="closeModal"
            >
              Cancel
            </button>
            <button type="submit" class="btn btn--full" :disabled="loading">
              {{ loading ? 'Creating\u2026' : 'Create Account' }}
            </button>
          </div>
        </form>
      </template>

      <template v-else>
        <h2 :id="dialogTitleId" class="modal-title">Complete Your Profile</h2>

        <div class="form-group">
          <label for="reg-program">Program (optional)</label>
          <select
            id="reg-program"
            ref="programSelect"
            v-model="selectedProgramId"
            name="program"
            class="form-control"
            aria-describedby="reg-program-help"
          >
            <option :value="null">Select your program</option>
            <option v-for="program in programs" :key="program.id" :value="program.id">
              {{ program.name }}
            </option>
          </select>
          <p id="reg-program-help" class="field-hint">Selecting a program loads its required courses.</p>
        </div>

        <div v-if="selectableRequirements.length > 0" class="courses-section">
          <p class="section-label">Check courses you have already completed</p>
          <ul class="course-list">
            <li v-for="requirement in selectableRequirements" :key="requirement.id" class="course-item">
              <label class="course-label">
                <input
                  type="checkbox"
                  :value="requirement.course_code"
                  :checked="isChecked(requirement.course_code)"
                  :aria-label="`Mark ${requirement.course_code} as completed`"
                  @change="toggleCourse(requirement.course_code)"
                />
                <span class="course-code">{{ requirement.course_code }}</span>
                <span v-if="requirement.description" class="course-desc">
                  - {{ requirement.description }}
                </span>
              </label>
              <input
                v-if="isChecked(requirement.course_code)"
                v-model="checkedCourses[requirement.course_code]"
                type="text"
                class="grade-input form-control"
                :aria-label="`Grade for ${requirement.course_code}`"
                placeholder="Grade (e.g. A)"
                maxlength="3"
              />
            </li>
          </ul>
        </div>

        <p v-if="error" data-testid="error-msg" class="error-text" aria-live="polite">{{ error }}</p>

        <div class="modal-actions">
          <button
            type="button"
            data-testid="finish-btn"
            class="btn btn--full"
            :disabled="loading"
            aria-label="Save completed courses"
            @click="submitStep2"
          >
            {{ loading ? 'Saving\u2026' : 'Finish' }}
          </button>
        </div>
      </template>

      <p class="modal__switch">
        Already have an account?
        <button
          type="button"
          class="link-btn"
          data-testid="switch-to-login"
          @click="emit('switch-to-login')"
        >
          Log in
        </button>
      </p>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-box {
  position: relative;
  background: #fff;
  width: 480px;
  max-width: 95vw;
  max-height: 90vh;
  overflow-y: auto;
  border-radius: 4px;
  padding: 28px 32px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
}

.modal__close {
  position: absolute;
  top: 10px;
  right: 10px;
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  padding: 6px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s, background 0.15s;
}

.modal__close:hover {
  color: #333;
  background: #f0f0f0;
}

.modal__close:focus-visible {
  outline: 2px solid #CFB87C;
  outline-offset: 1px;
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

.modal__switch {
  margin-top: 16px;
  font-size: 13px;
  color: #555;
  text-align: center;
}

.link-btn {
  background: none;
  border: none;
  color: #0277BD;
  cursor: pointer;
  font-size: 13px;
  padding: 0;
  text-decoration: underline;
}
</style>
