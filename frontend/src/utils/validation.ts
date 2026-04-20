// Mirrors the server-side password rule in
// services/course-search-api/course_search_api/routes/auth.py:90 (length >= 12).
// The common-password check stays server-side; its rejection is surfaced via
// the friendly error banner.
export const MIN_PASSWORD_LENGTH = 12

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function isNonEmpty(s: string): boolean {
  return s.trim().length > 0
}

export function isEmail(s: string): boolean {
  return EMAIL_RE.test(s.trim())
}

export function meetsPasswordPolicy(s: string): { ok: boolean; reason?: string } {
  if (s.length < MIN_PASSWORD_LENGTH) {
    return { ok: false, reason: `Password must be at least ${MIN_PASSWORD_LENGTH} characters.` }
  }
  return { ok: true }
}

export interface LoginFieldErrors {
  email?: string
  password?: string
}

export function validateLoginForm(input: { email: string; password: string }): LoginFieldErrors {
  const errors: LoginFieldErrors = {}
  if (!isNonEmpty(input.email)) {
    errors.email = 'Email is required.'
  } else if (!isEmail(input.email)) {
    errors.email = 'Enter a valid email address.'
  }
  if (!isNonEmpty(input.password)) {
    errors.password = 'Password is required.'
  }
  return errors
}

export interface RegisterStep1FieldErrors {
  name?: string
  email?: string
  password?: string
  confirmPassword?: string
}

export function validateRegisterStep1(input: {
  name: string
  email: string
  password: string
  confirmPassword: string
}): RegisterStep1FieldErrors {
  const errors: RegisterStep1FieldErrors = {}
  if (!isNonEmpty(input.name)) {
    errors.name = 'Name is required.'
  }
  if (!isNonEmpty(input.email)) {
    errors.email = 'Email is required.'
  } else if (!isEmail(input.email)) {
    errors.email = 'Enter a valid email address.'
  }
  const policy = meetsPasswordPolicy(input.password)
  if (!policy.ok) {
    errors.password = policy.reason
  }
  if (!isNonEmpty(input.confirmPassword)) {
    errors.confirmPassword = 'Please confirm your password.'
  } else if (input.password !== input.confirmPassword) {
    errors.confirmPassword = 'Passwords do not match.'
  }
  return errors
}

export function hasErrors<T extends object>(errors: T): boolean {
  return Object.values(errors).some((v) => typeof v === 'string' && v.length > 0)
}
