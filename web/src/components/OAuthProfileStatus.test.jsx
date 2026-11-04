import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { OAuthProfileStatus } from './OAuthProfileStatus.jsx'
import { api } from '../utils/studio.js'

vi.mock('../utils/studio.js', () => ({ api: vi.fn() }))
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })

it('issues a client credentials token by reference and shows metadata only', async () => {
  let connected = false
  api.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') { connected = true; return {} }
    return { configured: true, connected, grantType: 'client_credentials', expiresAt: '2030-01-01T00:00:00Z', canRefresh: false, accessToken: 'never-render' }
  })
  render(<OAuthProfileStatus projectRef="sample.json" name="service" environment="dev" profile={{ type: 'OAuth 2.0', grantType: 'client_credentials', issuer: 'https://issuer.example' }} actions />)
  const connect = await screen.findByRole('button', { name: '연결' })
  await waitFor(() => expect(connect).toBeEnabled())
  fireEvent.click(connect)
  await screen.findByText('연결됨')
  expect(api.mock.calls.find(([, options]) => options?.method === 'POST')).toEqual([
    '/api/projects/sample.json/oauth/profiles/service/token',
    { method: 'POST', body: JSON.stringify({ environment: 'dev', action: 'issue' }) },
  ])
  expect(screen.getByText(/Issuer:/)).toHaveTextContent('https://issuer.example')
  expect(screen.queryByText('never-render')).not.toBeInTheDocument()
})

it('opens the supplied authorization URL in a new tab without exposing code or token', async () => {
  const popup = { opener: {}, location: { replace: vi.fn() }, close: vi.fn() }
  const open = vi.spyOn(window, 'open').mockReturnValue(popup)
  api.mockImplementation(async (url, options) => options?.method === 'POST'
    ? { authorizationUrl: 'https://idp.example/authorize?state=opaque', callbackUri: 'https://studio.example/api/oauth/callback/provider' }
    : { configured: true, connected: false, grantType: 'authorization_code', canRefresh: false, callbackUri: 'https://studio.example/api/oauth/callback/provider' })
  render(<OAuthProfileStatus projectRef="sample.json" name="login" profile={{ type: 'OAuth 2.0', grantType: 'authorization_code' }} actions />)
  fireEvent.click(await screen.findByRole('button', { name: '인증 창 열기' }))
  await waitFor(() => expect(popup.location.replace).toHaveBeenCalledWith('https://idp.example/authorize?state=opaque'))
  expect(open).toHaveBeenCalledWith('about:blank', '_blank')
  expect(popup.opener).toBeNull()
  expect(api.mock.calls.find(([, options]) => options?.method === 'POST')[0]).toBe('/api/projects/sample.json/oauth/profiles/login/authorize')
  expect(screen.queryByText(/state=opaque/)).not.toBeInTheDocument()
})

it('uses a separate disconnect action and hides controls in read-only status views', async () => {
  api.mockResolvedValue({ configured: true, connected: true, grantType: 'authorization_code', canRefresh: true })
  const view = render(<OAuthProfileStatus projectRef="sample.json" name="login" profile={{ type: 'OAuth 2.0', grantType: 'authorization_code' }} actions />)
  fireEvent.click(await screen.findByRole('button', { name: '연결 해제' }))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/api/projects/sample.json/oauth/profiles/login', { method: 'DELETE' }))
  view.rerender(<OAuthProfileStatus projectRef="sample.json" name="login" profile={{ type: 'OAuth 2.0', grantType: 'authorization_code' }} />)
  expect(screen.queryByRole('button', { name: '연결 해제' })).not.toBeInTheDocument()
  expect(screen.getByText('만료 시각: 제공되지 않음')).toBeInTheDocument()
})

it('closes only its unused placeholder when selection changes before authorize returns', async () => {
  let completeAuthorize
  const popup = { opener: {}, location: { replace: vi.fn() }, close: vi.fn() }
  vi.spyOn(window, 'open').mockReturnValue(popup)
  api.mockImplementation(async (url, options) => options?.method === 'POST'
    ? new Promise(resolve => { completeAuthorize = resolve })
    : { configured: true, connected: false, grantType: 'authorization_code' })
  const profile = { type: 'OAuth 2.0', grantType: 'authorization_code' }
  const view = render(<OAuthProfileStatus projectRef="sample.json" name="login" environment="dev" profile={profile} actions />)
  fireEvent.click(await screen.findByRole('button', { name: '인증 창 열기' }))
  view.rerender(<OAuthProfileStatus projectRef="sample.json" name="other" environment="stage" profile={profile} actions />)
  completeAuthorize({ authorizationUrl: 'https://idp.example/authorize?state=old' })
  await waitFor(() => expect(popup.close).toHaveBeenCalledTimes(1))
  expect(popup.location.replace).not.toHaveBeenCalled()
  expect(screen.queryByText(/state=old/)).not.toBeInTheDocument()
})

it('refreshes a client credentials status once after an execution result changes', async () => {
  let connected = false
  api.mockImplementation(async () => ({ configured: true, connected, grantType: 'client_credentials', expiresAt: connected ? '2030-01-01T00:00:00Z' : '2020-01-01T00:00:00Z' }))
  const profile = { type: 'OAuth 2.0', grantType: 'client_credentials' }
  const view = render(<OAuthProfileStatus projectRef="sample.json" name="service" profile={profile} />)
  expect(await screen.findByText('실행 시 발급')).toBeInTheDocument()
  expect(screen.getByText(/API 실행 시 토큰을 자동 발급합니다/)).toBeInTheDocument()
  expect(api).toHaveBeenCalledTimes(1)
  connected = true
  view.rerender(<OAuthProfileStatus projectRef="sample.json" name="service" profile={profile} refreshKey={{ status: 200 }} />)
  expect(await screen.findByText('연결됨')).toBeInTheDocument()
  expect(api).toHaveBeenCalledTimes(2)
})
