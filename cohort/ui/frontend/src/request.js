let csrfToken = null
export const setCsrfToken = token => { csrfToken = token || null }

// The shell lives at the proxy's slash-terminated application URL. Resolve
// paths once here so a panel cannot accidentally escape to another app's API.
export function applicationPath(path, baseUrl = globalThis.document?.baseURI || 'http://localhost/') {
  if (!path.startsWith('/') || path.startsWith('//') || /(^|\/)\.{1,2}(\/|$)/.test(path)) {
    throw new Error('Expected an application-local path')
  }
  const base = new URL('.', baseUrl)
  const resolved = new URL(path.slice(1), base)
  if (!resolved.pathname.startsWith(base.pathname)) throw new Error('Path escapes the application')
  return resolved.pathname + resolved.search + resolved.hash
}

// All HTTP writes share this boundary; a new feature cannot accidentally omit
// session protection because it used a second fetch implementation.
export async function request(url, options = {}, fetcher = globalThis.fetch) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...options.headers }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const response = await fetcher(applicationPath(url), { ...options, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    const error = new Error(typeof detail === 'object' && detail !== null
      ? detail.rule ? `${detail.rule}: ${detail.message}` : detail.message || 'Request failed.'
      : detail || `${response.status} ${response.statusText}`)
    error.status = response.status
    error.rule = typeof detail === 'object' && detail !== null ? detail.rule : null
    error.code = typeof detail === 'object' && detail !== null ? detail.code : null
    if (response.status === 401 && !url.startsWith('/api/auth/')) {
      setCsrfToken(null)
      globalThis.window?.dispatchEvent(new Event('cohort:session-expired'))
    }
    throw error
  }
  return response.json()
}
