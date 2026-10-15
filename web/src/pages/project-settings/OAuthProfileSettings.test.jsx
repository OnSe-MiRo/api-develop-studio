import { expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { OAuthProfileSettings } from './OAuthProfileSettings.jsx'
import { api } from '../../utils/studio.js'

vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))

const props = () => ({
  projectReference: 'sample.json', authProfilesText: '{}', environmentsText: '{}',
  savedProjectForm: true,
  secretVariables: [{ name: 'client_secret', value: '', configured: true }],
  onAuthProfilesChange: vi.fn(), onEnvironmentsChange: vi.fn(),
})

it('builds a client credentials profile using only an encrypted variable reference', () => {
  const input = props()
  render(<OAuthProfileSettings {...input} />)
  fireEvent.change(screen.getByLabelText('새 프로필 이름'), { target: { value: 'service' } })
  fireEvent.change(screen.getByLabelText('Client ID'), { target: { value: 'studio-client' } })
  fireEvent.change(screen.getByLabelText('Token URL'), { target: { value: 'https://idp.example/token' } })
  fireEvent.change(screen.getByLabelText('Client Secret 변수'), { target: { value: '{{project.client_secret}}' } })
  fireEvent.change(screen.getByLabelText('Scopes (공백 구분)'), { target: { value: 'read,write profile' } })
  fireEvent.click(screen.getByRole('button', { name: '프로필을 JSON 설정에 적용' }))
  expect(JSON.parse(input.onAuthProfilesChange.mock.calls[0][0])).toEqual({
    service: { type: 'OAuth 2.0', grantType: 'client_credentials', clientId: 'studio-client', tokenUrl: 'https://idp.example/token', scopes: ['read,write', 'profile'], clientAuthMethod: 'basic', clientSecret: '{{project.client_secret}}' },
  })
  expect(input.onEnvironmentsChange).not.toHaveBeenCalled()
  expect(screen.queryByLabelText('Access Token')).not.toBeInTheDocument()
  expect(api).not.toHaveBeenCalled()
})

it('places a public PKCE profile in the selected environment without changing project profiles', () => {
  const input = { ...props(), environmentsText: JSON.stringify({ dev: { base_url: 'https://api.example' } }) }
  render(<OAuthProfileSettings {...input} />)
  fireEvent.change(screen.getByLabelText('설정 범위'), { target: { value: 'dev' } })
  fireEvent.change(screen.getByLabelText('새 프로필 이름'), { target: { value: 'userLogin' } })
  fireEvent.change(screen.getByLabelText('Grant'), { target: { value: 'authorization_code' } })
  fireEvent.change(screen.getByLabelText('Client 인증 방식'), { target: { value: 'none' } })
  fireEvent.change(screen.getByLabelText('Client ID'), { target: { value: 'public-app' } })
  fireEvent.change(screen.getByLabelText('Token URL'), { target: { value: 'https://idp.example/token' } })
  fireEvent.change(screen.getByLabelText('Authorization URL'), { target: { value: 'https://idp.example/authorize' } })
  fireEvent.click(screen.getByRole('button', { name: '프로필을 JSON 설정에 적용' }))
  const environments = JSON.parse(input.onEnvironmentsChange.mock.calls[0][0])
  expect(environments.dev.auth_profiles.userLogin).toMatchObject({ type: 'OAuth 2.0', grantType: 'authorization_code', clientAuthMethod: 'none', clientId: 'public-app', authorizationUrl: 'https://idp.example/authorize' })
  expect(environments.dev.auth_profiles.userLogin.clientSecret).toBeUndefined()
  expect(input.onAuthProfilesChange).not.toHaveBeenCalled()
})

it('keeps malformed JSON out of the structured editor', () => {
  const input = { ...props(), authProfilesText: '{' }
  render(<OAuthProfileSettings {...input} />)
  expect(screen.getByRole('alert')).toHaveTextContent('인증 프로필 JSON')
  expect(screen.queryByLabelText('Client ID')).not.toBeInTheDocument()
})

it('disables connection actions while the structured draft or project form is unsaved', () => {
  const profile = { type: 'OAuth 2.0', grantType: 'client_credentials', clientId: 'saved-client', tokenUrl: 'https://idp.example/token', scopes: [], clientAuthMethod: 'basic', clientSecret: '{{project.client_secret}}' }
  const input = { ...props(), authProfilesText: JSON.stringify({ service: profile }) }
  api.mockResolvedValue({ configured: true, connected: false, grantType: 'client_credentials' })
  const view = render(<OAuthProfileSettings {...input} />)
  fireEvent.change(screen.getByLabelText('기존 OAuth 프로필'), { target: { value: 'service' } })
  expect(screen.getByRole('button', { name: '연결' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Client ID'), { target: { value: 'unsaved-client' } })
  expect(screen.queryByRole('button', { name: '연결' })).not.toBeInTheDocument()
  expect(screen.getByText(/프로젝트에 저장한 뒤 연결/)).toBeInTheDocument()
  view.rerender(<OAuthProfileSettings {...input} savedProjectForm={false} />)
  expect(screen.queryByRole('button', { name: '연결' })).not.toBeInTheDocument()
})

it('shows a project OAuth profile inherited by an environment without removing the project definition', () => {
  const profile = { type: 'OAuth 2.0', grantType: 'authorization_code', clientId: 'app', tokenUrl: 'https://idp.example/token', authorizationUrl: 'https://idp.example/authorize', scopes: [], clientAuthMethod: 'none' }
  const input = { ...props(), authProfilesText: JSON.stringify({ login: profile }), environmentsText: JSON.stringify({ dev: { base_url: 'https://api.example' } }), savedProjectForm: false }
  render(<OAuthProfileSettings {...input} />)
  fireEvent.change(screen.getByLabelText('설정 범위'), { target: { value: 'dev' } })
  fireEvent.change(screen.getByLabelText('기존 OAuth 프로필'), { target: { value: 'login' } })
  expect(screen.getByText(/프로젝트 공통 프로필을 상속합니다/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '프로필 설정 제거' })).not.toBeInTheDocument()
})
