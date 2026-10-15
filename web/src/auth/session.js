let csrf = null
let namespace = ''
let workspace = null

export function configureSession(info) {
  csrf = info?.authenticated && info.mode === 'remote' ? info.csrfToken : null
  workspace = info?.authenticated && info.mode === 'remote' ? info.workspace?.id : null
  namespace = info?.authenticated && info.mode === 'remote' ? `${info.userId}:${info.workspace?.id || 'none'}:` : ''
}

export const jobNamespace = () => namespace

export async function authenticatedFetch(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  let request = options
  let target
  try { target = new URL(String(path), window.location.href) } catch { /* Invalid URLs fail in fetch. */ }
  const isApi = target?.origin === window.location.origin && target.pathname.startsWith('/api/')
  const isSession = target?.pathname.startsWith('/api/session')
  if (isApi && ((workspace && !isSession) || (csrf && !['GET', 'HEAD', 'OPTIONS'].includes(method)))) {
    const headers = new Headers(options.headers || {})
    if (workspace && !isSession) headers.set('X-Studio-Workspace', workspace)
    if (csrf && !['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-CSRF-Token', csrf)
    request = { ...options, headers }
  }
  const response = await fetch(path, request)
  if (isApi && [401, 403].includes(response.status) && !isSession) window.dispatchEvent(new Event('studio-auth-refresh'))
  return response
}

export async function sessionRequest(path, options) {
  const response = await authenticatedFetch(path, options)
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.error || '인증 요청을 처리하지 못했습니다.')
  return payload
}
