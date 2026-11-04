import { afterEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { PipelineAuthStatus } from './PipelineAuthStatus.jsx'
import { api } from '../../utils/studio.js'

vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
afterEach(() => vi.clearAllMocks())

it('shows the effective OAuth profile inherited from a pipeline case', async () => {
  api.mockImplementation(async path => path.startsWith('/api/cases/')
    ? { request: { auth_profile: 'login' } }
    : { configured: true, connected: true, grantType: 'authorization_code', expiresAt: '2030-01-01T00:00:00Z' })
  const view = render(<PipelineAuthStatus
    projectRef="sample.json"
    project={{ auth_profiles: { login: { type: 'OAuth 2.0', grantType: 'authorization_code' } } }}
    environment="dev"
    caseRefs={['tag/api/one.json', 'tag/api/one.json']}
  />)
  expect(await screen.findByText('연결됨')).toBeInTheDocument()
  expect(screen.getByText('tag/api/one.json')).toBeInTheDocument()
  expect(api).toHaveBeenCalledWith('/api/cases/tag%2Fapi%2Fone.json')
  expect(api).toHaveBeenCalledWith('/api/projects/sample.json/oauth/profiles/login?environment=dev')
  expect(api.mock.calls.filter(([path]) => path.startsWith('/api/cases/'))).toHaveLength(1)
  view.rerender(<PipelineAuthStatus
    projectRef="sample.json"
    project={{ auth_profiles: { login: { type: 'OAuth 2.0', grantType: 'authorization_code' } } }}
    environment="dev"
    caseRefs={['tag/api/one.json']}
    refreshKey="run-1:passed"
  />)
  await waitFor(() => expect(api.mock.calls.filter(([path]) => path.includes('/oauth/profiles/login'))).toHaveLength(2))
  expect(api.mock.calls.filter(([path]) => path.startsWith('/api/cases/'))).toHaveLength(1)
})
