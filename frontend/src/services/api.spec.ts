import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiFetch } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'

function mockFetch(body: unknown, status = 200): void {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response(JSON.stringify(body), { status }),
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

describe('apiFetch', () => {
  it('adds Authorization header when store has a token', async () => {
    const store = useAuthStore()
    store.setAuth('my-token', 1, 'Alice')
    mockFetch({ ok: true })
    await apiFetch('/api/courses')
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect((init?.headers as Record<string, string>)['Authorization']).toBe('Bearer my-token')
  })

  it('does NOT add Authorization header when store has no token', async () => {
    mockFetch({ ok: true })
    await apiFetch('/api/courses')
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect((init?.headers as Record<string, string>)['Authorization']).toBeUndefined()
  })

  it('does NOT add Authorization header for non-/api/ URLs', async () => {
    const store = useAuthStore()
    store.setAuth('my-token', 1, 'Alice')
    mockFetch({ ok: true })
    await apiFetch('/public/something')
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect((init?.headers as Record<string, string>)['Authorization']).toBeUndefined()
  })

  it('calls store.logout() on 401 response from /api/ URL', async () => {
    const store = useAuthStore()
    store.setAuth('expired-tok', 1, 'Alice')
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 401 }))
    await apiFetch('/api/courses')
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
  })

  it('does NOT call store.logout() on 401 from non-/api/ URL', async () => {
    const store = useAuthStore()
    store.setAuth('tok', 1, 'Alice')
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 401 }))
    await apiFetch('/external/thing')
    expect(store.isAuthenticated).toBe(true)
    expect(store.token).toBe('tok')
  })

  it('returns the response without throwing on 401', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(null, { status: 401 }))
    const res = await apiFetch('/api/courses')
    expect(res.status).toBe(401)
  })

  it('adds Content-Type: application/json when body is present', async () => {
    mockFetch({ ok: true })
    await apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: 'a@b.com' }) })
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('does NOT override an explicit Content-Type header', async () => {
    mockFetch({ ok: true })
    await apiFetch('/api/test', {
      method: 'POST',
      body: 'data',
      headers: { 'Content-Type': 'text/plain' },
    })
    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('text/plain')
  })
})
