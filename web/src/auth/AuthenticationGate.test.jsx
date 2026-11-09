import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AuthenticationGate } from './AuthenticationGate.jsx'
import { configureSession, jobNamespace } from './session.js'
const session = { mode: 'remote', authenticated: true, loginAvailable: true, userId: 'alice', displayName: 'Alice', workspace: { id: 'a', name: 'A', role: 'owner' }, workspaces: [{ id: 'a', name: 'A', role: 'owner' }, { id: 'b', name: 'B', role: 'viewer' }], csrfToken: 'csrf-value' }
beforeEach(() => { window.history.replaceState(null, '', '/projects') })
afterEach(() => { configureSession(null); vi.unstubAllGlobals() })
it('does not mount private app data until the session is authenticated', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ mode: 'remote', authenticated: false, loginAvailable: true }) }))
  render(<AuthenticationGate>{() => <div>Private app</div>}</AuthenticationGate>)
  expect(await screen.findByRole('link', { name: 'SSO 로그인' })).toHaveAttribute('href', '/auth/login')
  expect(screen.queryByText('Private app')).not.toBeInTheDocument()
})
it('switches workspace with CSRF and clears old route context', async () => {
  const fetch = vi.fn().mockImplementation(async path => ({ ok: true, status: 200, json: async () => path.endsWith('/workspace') ? { ...session, workspace: session.workspaces[1] } : session }))
  vi.stubGlobal('fetch', fetch)
  const navigate = vi.fn()
  render(<AuthenticationGate onNavigate={navigate}>{(info, actions) => <><div>{info.workspace.id}</div><button onClick={() => actions.switchWorkspace('b')}>Switch</button></>}</AuthenticationGate>)
  fireEvent.click(await screen.findByRole('button', { name: 'Switch' }))
  await waitFor(() => expect(navigate).toHaveBeenCalledWith('/projects'))
  expect(jobNamespace()).toBe('alice:a:')
  expect(window.location.pathname).toBe('/projects')
  const request = fetch.mock.calls.find(([path]) => path.endsWith('/workspace'))[1]
  expect(request.headers.get('X-CSRF-Token')).toBe('csrf-value')
})
it('shows a workspace chooser after current membership is revoked', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ...session, workspace: null }) }))
  render(<AuthenticationGate>{() => <div>Private app</div>}</AuthenticationGate>)
  expect(await screen.findByRole('heading', { name: 'Workspace 선택' })).toBeInTheDocument()
  expect(screen.queryByText('Private app')).not.toBeInTheDocument()
})
it('clears private app state and CSRF after logout', async () => {
  const fetch = vi.fn().mockImplementation(async path => ({ ok: true, status: 200, json: async () => path.endsWith('/logout') ? { loggedOut: true } : session }))
  vi.stubGlobal('fetch', fetch)
  render(<AuthenticationGate>{(_info, actions) => <button onClick={actions.logout}>Logout</button>}</AuthenticationGate>)
  fireEvent.click(await screen.findByRole('button', { name: 'Logout' }))
  await screen.findByRole('link', { name: 'SSO 로그인' })
  expect(jobNamespace()).toBe('')
})

it('unmounts a selected dashboard detail before navigating away on workspace switch', async () => {
  window.history.replaceState(null,'','/dashboard?project=demo&days=30&page=2&run=old-run')
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async path=>({ok:true,status:200,json:async()=>path.endsWith('/workspace')?{...session,workspace:session.workspaces[1]}:session})))
  const navigate=vi.fn()
  render(<AuthenticationGate onNavigate={navigate}>{(_info,actions)=><div><p>Private old-run detail</p><button onClick={()=>actions.switchWorkspace('b')}>Switch workspace</button></div>}</AuthenticationGate>)
  fireEvent.click(await screen.findByRole('button',{name:'Switch workspace'}))
  await waitFor(()=>expect(navigate).toHaveBeenCalledWith('/projects'))
  expect(screen.queryByText('Private old-run detail')).not.toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('인증 상태를 변경하고 있습니다')
})

it('submits the public signup form and returns to SSO without mounting private pages', async () => {
  const fetch = vi.fn().mockImplementation(async path => ({
    ok: true, json: async () => path === '/api/session'
      ? { authenticated: false, mode: 'remote', loginAvailable: true, signupAvailable: true } : {},
  }))
  vi.stubGlobal('fetch', fetch)
  render(<AuthenticationGate>{() => <div>Private app</div>}</AuthenticationGate>)
  fireEvent.click(await screen.findByRole('button', { name: '회원가입' }))
  fireEvent.change(screen.getByLabelText('이메일'), { target: { value: 'tester@example.test' } })
  expect(screen.getByLabelText('비밀번호 (8자 이상)')).toHaveAttribute('minlength', '8')
  fireEvent.change(screen.getByLabelText('비밀번호 (8자 이상)'), { target: { value: 'signup-8' } })
  fireEvent.change(screen.getByLabelText('비밀번호 확인'), { target: { value: 'signup-8' } })
  fireEvent.click(screen.getByRole('button', { name: '계정 만들기' }))
  expect(await screen.findByRole('link', { name: 'SSO 로그인' })).toHaveAttribute('href', '/auth/login')
  expect(JSON.parse(fetch.mock.calls.find(([path]) => path === '/auth/signup')[1].body)).toEqual({ email: 'tester@example.test', password: 'signup-8' })
  expect(screen.queryByText('Private app')).not.toBeInTheDocument()
})
