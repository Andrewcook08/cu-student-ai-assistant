<script setup lang="ts">
import { ref } from 'vue'
import { useAuth } from '@/composables/useAuth'

const emit = defineEmits<{
  close: []
  'switch-to-register': []
}>()

const { login, loading, error } = useAuth()

const email = ref('')
const password = ref('')

async function handleSubmit() {
  try {
    await login({ email: email.value, password: password.value })
    emit('close')
  } catch {
    // error is set by useAuth
  }
}
</script>

<template>
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="login-title">
    <div class="modal-box">
      <h2 id="login-title" class="modal__title">Log In</h2>

      <form @submit.prevent="handleSubmit" novalidate>
        <div class="form-group">
          <label for="login-email" class="form-label">Email</label>
          <input
            id="login-email"
            v-model="email"
            type="email"
            class="form-control"
            autocomplete="email"
            required
          />
        </div>

        <div class="form-group">
          <label for="login-password" class="form-label">Password</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            class="form-control"
            autocomplete="current-password"
            required
          />
        </div>

        <p
          v-if="error"
          data-testid="error-msg"
          class="modal__error"
          role="alert"
        >{{ error }}</p>

        <div class="modal__actions">
          <button
            type="button"
            class="btn btn--secondary"
            data-testid="cancel-btn"
            @click="emit('close')"
          >
            Cancel
          </button>
          <button
            type="submit"
            class="btn btn--full"
            :disabled="loading"
          >
            {{ loading ? 'Logging in…' : 'Log In' }}
          </button>
        </div>
      </form>

      <p class="modal__switch">
        Don't have an account?
        <button
          type="button"
          class="link-btn"
          data-testid="switch-to-register"
          @click="emit('switch-to-register')"
        >
          Register
        </button>
      </p>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-box {
  background: #fff;
  border-radius: 4px;
  padding: 24px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.18);
}

.modal__title {
  margin: 0 0 20px;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  color: #555;
}

.form-control {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #ccc;
  border-radius: 3px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-control:focus {
  outline: 2px solid #CFB87C;
  outline-offset: 1px;
}

.modal__error {
  color: #c0392b;
  font-size: 13px;
  margin: 0 0 12px;
}

.modal__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 20px;
}

.btn {
  padding: 7px 16px;
  border: none;
  border-radius: 3px;
  font-size: 13px;
  cursor: pointer;
}

.btn--full {
  background: #CFB87C;
  color: #000;
  font-weight: 600;
}

.btn--full:hover:not(:disabled) {
  background: #c4a94f;
}

.btn--full:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn--secondary {
  background: #f5f5f5;
  color: #333;
  border: 1px solid #ccc;
}

.btn--secondary:hover {
  background: #eee;
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
