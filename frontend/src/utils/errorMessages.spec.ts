import { describe, it, expect } from 'vitest'
import { friendlyHttpError, extractApiError } from './errorMessages'

describe('friendlyHttpError', () => {
  it('auth + 401 → "Invalid email or password."', () => {
    expect(friendlyHttpError(401, 'auth')).toBe('Invalid email or password.')
  })

  it('auth + 409 → "already exists" copy', () => {
    expect(friendlyHttpError(409, 'auth')).toContain('already exists')
  })

  it('courses + 404 → "couldn\'t find that course"', () => {
    expect(friendlyHttpError(404, 'courses')).toContain("couldn't find that course")
  })

  it('profile + 403 → "not allowed to update"', () => {
    expect(friendlyHttpError(403, 'profile')).toContain('not allowed')
  })

  it('5xx falls back to the 5xx bucket', () => {
    expect(friendlyHttpError(502, 'courses')).toContain('loading courses')
    expect(friendlyHttpError(503, 'auth')).toContain('our end')
  })

  it('unknown status falls back to the default copy', () => {
    expect(friendlyHttpError(418, 'generic')).toBe('Something went wrong. Please try again.')
  })
})

describe('extractApiError', () => {
  async function makeResponse(body: unknown, status = 400): Promise<Response> {
    return new Response(body === null ? null : JSON.stringify(body), { status })
  }

  it('prefers backend detail when it is a short sentence', async () => {
    const res = await makeResponse({ detail: 'Password is too common — choose a more unique password' }, 400)
    await expect(extractApiError(res, 'auth')).resolves.toContain('too common')
  })

  it('falls back to category copy when detail is missing', async () => {
    const res = await makeResponse({}, 401)
    await expect(extractApiError(res, 'auth')).resolves.toBe('Invalid email or password.')
  })

  it('falls back to category copy when body is non-JSON', async () => {
    const res = new Response('<html>Server Error</html>', { status: 500 })
    await expect(extractApiError(res, 'courses')).resolves.toContain('loading courses')
  })

  it('falls back when body is empty', async () => {
    const res = new Response(null, { status: 500 })
    await expect(extractApiError(res, 'generic')).resolves.toBe(
      'Something went wrong on our end. Please try again.',
    )
  })

  it('rejects detail containing HTML tags (treats as untrusted)', async () => {
    const res = await makeResponse({ detail: '<script>alert(1)</script>' }, 400)
    // Should NOT surface raw HTML — fall back to friendly copy
    const result = await extractApiError(res, 'auth')
    expect(result).not.toContain('<script>')
  })

  it('rejects detail containing newlines (looks like a stack trace)', async () => {
    const res = await makeResponse({ detail: 'Error\nat foo.py:12' }, 500)
    const result = await extractApiError(res, 'generic')
    expect(result).not.toContain('foo.py')
  })

  it('rejects excessively long detail', async () => {
    const res = await makeResponse({ detail: 'x'.repeat(500) }, 400)
    const result = await extractApiError(res, 'auth')
    expect(result.length).toBeLessThan(200)
  })

  it('preserves list-shaped detail by falling back (FastAPI validation errors)', async () => {
    const res = await makeResponse({ detail: [{ msg: 'field required' }] }, 422)
    const result = await extractApiError(res, 'auth')
    // `detail` is not a string here → fall back
    expect(result).toBe('Please check your input and try again.')
  })
})
