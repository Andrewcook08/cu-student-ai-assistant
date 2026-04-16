import { useAuthStore } from '@/stores/authStore'

export async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const store = useAuthStore()
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> ?? {}) }
  const isApiCall = url.startsWith('/api/')

  if (store.token && isApiCall) {
    headers['Authorization'] = `Bearer ${store.token}`
  }

  if (init.body !== undefined && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(url, { ...init, headers })

  // Only clear auth state on 401 from our own API. A 401 from an unrelated URL
  // (e.g. a third-party endpoint the caller passed in) shouldn't log the user
  // out of our app.
  if (res.status === 401 && isApiCall) {
    store.logout()
  }

  return res
}
