import { useAuthStore } from '@/stores/authStore'

export async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const store = useAuthStore()
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> ?? {}) }

  if (store.token && url.startsWith('/api/')) {
    headers['Authorization'] = `Bearer ${store.token}`
  }

  if (init.body !== undefined && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(url, { ...init, headers })

  if (res.status === 401) {
    store.logout()
  }

  return res
}
