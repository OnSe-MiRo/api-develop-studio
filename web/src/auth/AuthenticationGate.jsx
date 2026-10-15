import { useEffect, useRef, useState } from 'react'
import { configureSession, sessionRequest } from './session.js'

export function AuthenticationGate({ children, onNavigate = target => window.location.assign(target) }) {
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const loading = useRef(false)
  const mutating = useRef(false)
  const identity = useRef('')
  const generation = useRef(0)
  const mounted = useRef(true)
  const refresh = async () => {
    if (loading.current || mutating.current) return
    const current = generation.current
    loading.current = true
    try {
      const session = await sessionRequest('/api/session')
      if (mounted.current && current === generation.current) {
        const key = session.authenticated ? `${session.mode}:${session.userId}:${session.workspace?.id || 'none'}` : ''
        if (key && identity.current && key !== identity.current) { setBusy(true); onNavigate('/projects'); return }
        if (key) identity.current = key
        configureSession(session); setInfo(session); setError('')
      }
    } catch (failure) { if (mounted.current && current === generation.current) setError(failure.message) }
    finally { loading.current = false }
  }
  useEffect(() => {
    mounted.current = true; refresh()
    const focus = () => refresh()
    window.addEventListener('studio-auth-refresh', focus); window.addEventListener('focus', focus)
    return () => { mounted.current = false; window.removeEventListener('studio-auth-refresh', focus); window.removeEventListener('focus', focus) }
  }, [])
  const switchWorkspace = async workspaceId => {
    if (!workspaceId || mutating.current) return
    ++generation.current; mutating.current = true
    setBusy(true); setError('')
    try {
      const session = await sessionRequest('/api/session/workspace', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ workspaceId }) })
      // Old async requests retain the old workspace header until a new JS realm loads.
      onNavigate('/projects')
    } catch (failure) { setError(failure.message); mutating.current = false; setBusy(false); await refresh() }
  }
  const logout = async () => {
    if (mutating.current) return
    ++generation.current; mutating.current = true
    setBusy(true); setError('')
    try {
      await sessionRequest('/api/session/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      configureSession(null); setInfo({ mode: 'remote', authenticated: false, loginAvailable: true })
    } catch (failure) { setError(failure.message) }
    finally { mutating.current = false; setBusy(false) }
  }
  const loginError = new URLSearchParams(window.location.search).get('loginError')
  if (busy) return <main className="card login-card" role="status">인증 상태를 변경하고 있습니다…</main>
  if (!info || !info.authenticated || !info.workspace) return <main className="card login-card">
    <p className="eyebrow">API DEVELOP STUDIO</p><h1>{!info ? '로그인 상태 확인' : info.authenticated ? 'Workspace 선택' : '로그인이 필요합니다'}</h1>
    {loginError && <p className="notice" role="alert">로그인을 완료하지 못했습니다. 계정 등록과 SSO 설정을 확인하거나 다시 시도하세요. ({['identity_not_registered', 'workspace_membership_required', 'id_token_invalid', 'login_state_invalid', 'provider_login_denied'].includes(loginError) ? loginError : 'login_failed'})</p>}
    {error && <p role="alert">{error}</p>}
    {!info && !error && <p>서버에서 로그인 상태를 확인하고 있습니다.</p>}
    {info?.authenticated && !info.workspace && <><p>접근할 Workspace를 선택하세요. 목록이 없으면 관리자에게 membership을 요청하세요.</p><label>Workspace<select disabled={busy} value="" onChange={e => switchWorkspace(e.target.value)}><option value="">선택</option>{info.workspaces.map(item => <option key={item.id} value={item.id}>{item.name} · {item.role}</option>)}</select></label><button className="ghost" disabled={busy} onClick={logout}>Studio 로그아웃</button></>}
    {!info?.authenticated && info?.loginAvailable && <a className="primary login-link" href="/auth/login">SSO 로그인</a>}
    {info && !info.authenticated && !info.loginAvailable && <p className="notice">서버의 OIDC 설정이 아직 준비되지 않았습니다. 관리자에게 설정을 요청하세요.</p>}
    <button className="ghost" disabled={loading.current} onClick={refresh}>상태 다시 확인</button>
  </main>
  return <>{error && <p className="notice" role="alert">{error}</p>}{children(info, { switchWorkspace, logout, busy })}</>
}

export function SessionControls({ info, actions, onManage }) {
  if (!info) return null
  return <div className="session-controls"><span>{info.displayName} · {info.mode === 'local' ? '로컬 모드' : info.workspace?.role}</span>
    {info.mode === 'remote' && <><label>Workspace<select aria-label="현재 Workspace" disabled={actions.busy} value={info.workspace.id} onChange={e => actions.switchWorkspace(e.target.value)}>{info.workspaces.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button className="ghost" disabled={actions.busy} onClick={actions.logout}>Studio 로그아웃</button></>}
    {['owner', 'admin'].includes(info.workspace?.role) && <button className="ghost" onClick={onManage}>멤버·감사 기록</button>}
  </div>
}
