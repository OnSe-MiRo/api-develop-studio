import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../utils/studio.js'

const statusPath = (projectRef, name, environment) =>
  `/api/projects/${encodeURIComponent(projectRef)}/oauth/profiles/${encodeURIComponent(name)}${environment ? `?environment=${encodeURIComponent(environment)}` : ''}`
const profilePath = (projectRef, name) =>
  `/api/projects/${encodeURIComponent(projectRef)}/oauth/profiles/${encodeURIComponent(name)}`

const expiresLabel = value => {
  if (!value) return ''
  const date = new Date(typeof value === 'number' ? value * 1000 : value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('ko-KR')
}

function OAuthProfileStatus({ projectRef, name, environment = '', profile, actions = false, enabled = true, refreshKey = null }) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const requestId = useRef(0)
  const actionScope = useRef(0)
  const lastRefreshKey = useRef(refreshKey)
  const basePath = projectRef && name ? profilePath(projectRef, name) : ''
  const path = basePath ? statusPath(projectRef, name, environment) : ''
  const load = useCallback(async () => {
    if (!path || !enabled) return
    const id = ++requestId.current
    setLoading(true)
    try {
      const next = await api(path)
      if (requestId.current !== id) return
      setStatus(next); setError('')
      if (next.connected) setPending(false)
    } catch (issue) { if (requestId.current === id) { setStatus(null); setError(issue.message) } }
    finally { if (requestId.current === id) setLoading(false) }
  }, [path, enabled])
  useEffect(() => {
    setStatus(null); setError(''); setNotice(''); setPending(false); setBusy(false)
    if (path && enabled) load()
    return () => { requestId.current += 1; actionScope.current += 1 }
  }, [path, enabled, load])
  useEffect(() => {
    if (!path || !enabled) return undefined
    const refresh = () => { if (document.visibilityState === 'visible') load() }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => { window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh) }
  }, [path, enabled, load])
  useEffect(() => {
    if (refreshKey === null || refreshKey === undefined || lastRefreshKey.current === refreshKey) return
    lastRefreshKey.current = refreshKey
    load()
  }, [refreshKey, load])
  useEffect(() => {
    if (!pending) return undefined
    const timer = window.setInterval(load, 3000)
    const deadline = window.setTimeout(() => setPending(false), 120000)
    return () => { window.clearInterval(timer); window.clearTimeout(deadline) }
  }, [pending, load])
  const tokenAction = async action => {
    const scope = actionScope.current
    setBusy(true); setError(''); setNotice('')
    try {
      await api(`${basePath}/token`, { method: 'POST', body: JSON.stringify({ environment, action }) })
      if (actionScope.current !== scope) return
      setNotice(action === 'refresh' ? 'OAuth 연결을 갱신했습니다.' : 'OAuth 연결을 완료했습니다.')
      await load()
    } catch (issue) { if (actionScope.current === scope) setError(issue.message) }
    finally { if (actionScope.current === scope) setBusy(false) }
  }
  const authorize = async () => {
    const popup = window.open('about:blank', '_blank')
    if (!popup) { setError('인증 창을 열 수 없습니다. 브라우저의 팝업 허용을 확인하세요.'); return }
    popup.opener = null
    const scope = actionScope.current
    let navigated = false
    setBusy(true); setError(''); setNotice('')
    try {
      const response = await api(`${basePath}/authorize`, { method: 'POST', body: JSON.stringify({ environment }) })
      if (actionScope.current !== scope) { popup.close(); return }
      const url = new URL(response.authorizationUrl)
      if (!['http:', 'https:'].includes(url.protocol)) throw new Error('인증 URL 형식이 올바르지 않습니다.')
      popup.location.replace(url.href)
      navigated = true
      setPending(true)
      setNotice('새 창에서 인증을 완료하면 연결 상태가 갱신됩니다.')
    } catch (issue) { if (!navigated) popup.close(); if (actionScope.current === scope) setError(issue.message) }
    finally { if (actionScope.current === scope) setBusy(false) }
  }
  const disconnect = async () => {
    const scope = actionScope.current
    setBusy(true); setError(''); setNotice('')
    try {
      await api(path, { method: 'DELETE' })
      if (actionScope.current !== scope) return
      setPending(false); setNotice('OAuth 연결을 해제했습니다.')
      await load()
    } catch (issue) { if (actionScope.current === scope) setError(issue.message) }
    finally { if (actionScope.current === scope) setBusy(false) }
  }
  if (!projectRef || !name || profile?.type !== 'OAuth 2.0') return null
  if (!enabled) return <p className="hint">이 OAuth 설정을 프로젝트에 저장한 뒤 연결할 수 있습니다.</p>
  return <div className="oauth-status" aria-label={`${name} OAuth 상태`}>
    <div className="oauth-status-heading"><strong>{name}</strong><span>{loading ? '상태 확인 중…' : status?.connected ? '연결됨' : status?.configured && profile.grantType === 'client_credentials' ? '실행 시 발급' : status?.configured ? '연결 필요' : '설정 필요'}</span></div>
    {profile.issuer && <p className="hint">Issuer: <code>{profile.issuer}</code></p>}
    {status?.expiresAt && <p className="hint">{status.connected ? '만료 시각' : '마지막 만료 시각'}: {expiresLabel(status.expiresAt)}</p>}
    {status?.connected && !status.expiresAt && <p className="hint">만료 시각: 제공되지 않음</p>}
    {status?.callbackUri && actions && <p className="hint">Callback URI: <code>{status.callbackUri}</code></p>}
    {actions && <div className="actions">
      {profile.grantType === 'authorization_code' ? <button className="ghost" disabled={busy || loading || !status?.configured} onClick={authorize}>{status?.connected ? '다시 연결' : '인증 창 열기'}</button> : <button className="ghost" disabled={busy || loading || !status?.configured} onClick={() => tokenAction('issue')}>{status?.connected ? '재발급' : '연결'}</button>}
      {status?.canRefresh && <button className="ghost" disabled={busy || loading} onClick={() => tokenAction('refresh')}>갱신</button>}
      {status?.connected && <button className="danger-button" disabled={busy || loading} onClick={disconnect}>연결 해제</button>}
      <button className="ghost" disabled={busy || loading} onClick={load}>상태 새로고침</button>
    </div>}
    {!actions && status && !status.connected && <p className="hint">{profile.grantType === 'client_credentials' && status.configured ? 'API 실행 시 토큰을 자동 발급합니다. 사전 발급은 프로젝트 설정에서 할 수 있습니다.' : '프로젝트 설정에서 인증 창 연결이 필요합니다.'}</p>}
    {pending && <p className="hint">인증 완료를 기다리는 중입니다.</p>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {error && <p className="notice" role="alert">{error}</p>}
  </div>
}

export { OAuthProfileStatus, statusPath }
