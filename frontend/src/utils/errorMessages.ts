export type ErrorCategory = 'auth' | 'courses' | 'profile' | 'generic'

// Human-readable copy per category + status. Keeps raw status codes off the
// UI surface. When the backend returns a sentence-like `detail`, prefer that
// (the server often has better context — e.g. "Password is too common").
const CATEGORY_COPY: Record<ErrorCategory, Record<string, string>> = {
  auth: {
    '400': 'Please check your input and try again.',
    '401': 'Invalid email or password.',
    '403': 'You are not allowed to do that.',
    '404': "We couldn't find that account.",
    '409': 'An account with that email already exists.',
    '422': 'Please check your input and try again.',
    '429': 'Too many attempts. Please wait a moment and try again.',
    '5xx': 'Something went wrong on our end. Please try again.',
    default: 'Something went wrong. Please try again.',
  },
  courses: {
    '400': 'Please check your search and try again.',
    '401': 'Please log in to continue.',
    '403': 'You are not allowed to view that.',
    '404': "We couldn't find that course.",
    '429': 'Too many requests. Please wait a moment and try again.',
    '5xx': 'Something went wrong loading courses. Please try again.',
    default: 'Something went wrong loading courses.',
  },
  profile: {
    '400': 'Please check your input and try again.',
    '401': 'Please log in to continue.',
    '403': 'You are not allowed to update that.',
    '404': "We couldn't find that record.",
    '422': 'Please check your input and try again.',
    '5xx': 'Something went wrong saving your profile. Please try again.',
    default: 'Something went wrong saving your profile.',
  },
  generic: {
    '5xx': 'Something went wrong on our end. Please try again.',
    default: 'Something went wrong. Please try again.',
  },
}

export function friendlyHttpError(status: number, category: ErrorCategory): string {
  const copy = CATEGORY_COPY[category]
  const exact = copy[String(status)]
  if (exact) return exact
  if (status >= 500 && status < 600 && copy['5xx']) return copy['5xx']
  return copy.default
}

// A `detail` string is trustworthy for UI when it looks like a short sentence
// (not an HTML blob, not a stack trace, not a raw exception repr).
function looksLikeSentence(s: string): boolean {
  const trimmed = s.trim()
  if (trimmed.length === 0 || trimmed.length > 200) return false
  if (trimmed.includes('<') || trimmed.includes('>')) return false
  if (trimmed.includes('\n')) return false
  return true
}

export async function extractApiError(
  response: Response,
  category: ErrorCategory,
): Promise<string> {
  let detail: string | null = null
  try {
    const body: unknown = await response.clone().json()
    if (
      body !== null &&
      typeof body === 'object' &&
      'detail' in body &&
      typeof (body as { detail: unknown }).detail === 'string'
    ) {
      const candidate = (body as { detail: string }).detail
      if (looksLikeSentence(candidate)) {
        detail = candidate
      }
    }
  } catch {
    // non-JSON body — fall through to friendly copy
  }
  return detail ?? friendlyHttpError(response.status, category)
}
