import { describe, it, expect } from 'vitest'
import {
  isNonEmpty,
  isEmail,
  meetsPasswordPolicy,
  validateLoginForm,
  validateRegisterStep1,
  hasErrors,
  MIN_PASSWORD_LENGTH,
} from './validation'

describe('isNonEmpty', () => {
  it('returns false for empty string', () => {
    expect(isNonEmpty('')).toBe(false)
  })

  it('returns false for whitespace-only string', () => {
    expect(isNonEmpty('   \t\n')).toBe(false)
  })

  it('returns true for non-empty string', () => {
    expect(isNonEmpty('hello')).toBe(true)
  })
})

describe('isEmail', () => {
  it('accepts common formats', () => {
    expect(isEmail('a@b.com')).toBe(true)
    expect(isEmail('alice.smith+tag@example.co.uk')).toBe(true)
  })

  it('rejects missing @', () => {
    expect(isEmail('abc.com')).toBe(false)
  })

  it('rejects missing domain', () => {
    expect(isEmail('a@')).toBe(false)
  })

  it('rejects whitespace in address', () => {
    expect(isEmail('a b@c.com')).toBe(false)
  })

  it('trims surrounding whitespace before validating', () => {
    expect(isEmail('  a@b.com  ')).toBe(true)
  })
})

describe('meetsPasswordPolicy', () => {
  it(`rejects passwords shorter than ${MIN_PASSWORD_LENGTH}`, () => {
    const result = meetsPasswordPolicy('short')
    expect(result.ok).toBe(false)
    expect(result.reason).toContain(String(MIN_PASSWORD_LENGTH))
  })

  it(`accepts passwords of exactly ${MIN_PASSWORD_LENGTH} chars`, () => {
    expect(meetsPasswordPolicy('a'.repeat(MIN_PASSWORD_LENGTH)).ok).toBe(true)
  })

  it('accepts long passwords', () => {
    expect(meetsPasswordPolicy('a'.repeat(32)).ok).toBe(true)
  })
})

describe('validateLoginForm', () => {
  it('flags empty email + password', () => {
    const errors = validateLoginForm({ email: '', password: '' })
    expect(errors.email).toBeDefined()
    expect(errors.password).toBeDefined()
  })

  it('flags whitespace-only email', () => {
    const errors = validateLoginForm({ email: '   ', password: 'xxxxxxxxxxxx' })
    expect(errors.email).toBeDefined()
  })

  it('flags malformed email', () => {
    const errors = validateLoginForm({ email: 'not-an-email', password: 'xxxxxxxxxxxx' })
    expect(errors.email).toBe('Enter a valid email address.')
  })

  it('returns no errors for valid input', () => {
    const errors = validateLoginForm({ email: 'a@b.com', password: 'anything' })
    expect(errors).toEqual({})
  })
})

describe('validateRegisterStep1', () => {
  const valid = {
    name: 'Alice',
    email: 'a@b.com',
    password: 'a'.repeat(MIN_PASSWORD_LENGTH),
    confirmPassword: 'a'.repeat(MIN_PASSWORD_LENGTH),
  }

  it('returns no errors for valid input', () => {
    expect(validateRegisterStep1(valid)).toEqual({})
  })

  it('flags empty name', () => {
    const errors = validateRegisterStep1({ ...valid, name: '' })
    expect(errors.name).toBeDefined()
  })

  it('flags malformed email', () => {
    const errors = validateRegisterStep1({ ...valid, email: 'bad' })
    expect(errors.email).toBeDefined()
  })

  it('flags short password', () => {
    const errors = validateRegisterStep1({
      ...valid,
      password: 'short',
      confirmPassword: 'short',
    })
    expect(errors.password).toBeDefined()
  })

  it('flags mismatched confirm password', () => {
    const errors = validateRegisterStep1({
      ...valid,
      confirmPassword: 'different-12-chars',
    })
    expect(errors.confirmPassword).toBe('Passwords do not match.')
  })

  it('flags empty confirm password even when password is valid', () => {
    const errors = validateRegisterStep1({ ...valid, confirmPassword: '' })
    expect(errors.confirmPassword).toBeDefined()
  })
})

describe('hasErrors', () => {
  it('returns true when any field has a message', () => {
    expect(hasErrors({ email: 'bad' })).toBe(true)
  })

  it('returns false when all fields are undefined', () => {
    expect(hasErrors({ email: undefined })).toBe(false)
  })

  it('returns false for an empty object', () => {
    expect(hasErrors({})).toBe(false)
  })
})
