import { act, fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App.jsx'

const pending = vi.hoisted(() => {
  let openApiCall
  let openMembers
  return {
    apiCall: new Promise(resolve => { openApiCall = resolve }),
    members: new Promise(resolve => { openMembers = resolve }),
    openApiCall: () => openApiCall(),
    openMembers: () => openMembers(),
  }
})

vi.mock('./utils/studio.js', () => ({ api: vi.fn().mockResolvedValue({ items: [] }) }))
vi.mock('./auth/AuthenticationGate.jsx', async importOriginal => ({
  ...await importOriginal(),
  AuthenticationGate: ({ children }) => children({ userId: 'test', mode: 'local', workspace: { id: 'team', role: 'owner' } }, {}),
}))
vi.mock('./pages/api-call/ApiCallPage.jsx', async () => {
  await pending.apiCall
  return { ApiCallPage: () => <h1>API 호출 화면</h1> }
})
vi.mock('./auth/WorkspaceMembers.jsx', async () => {
  await pending.members
  return { WorkspaceMembers: () => <h1>Workspace 멤버·감사 기록</h1> }
})
vi.mock('./pages/projects/ProjectList.jsx', () => ({ ProjectList: () => <h1>프로젝트 화면</h1> }))
vi.mock('./pages/apis/ApiList.jsx', () => ({ get ApiList() { throw new Error('화면 파일을 다운로드하지 못했습니다.') } }))

it('keeps navigation available while a page loads and ignores a late page after navigation', async () => {
  window.history.replaceState(null, '', '/api-call')
  render(<App />)
  expect(screen.getByRole('status')).toHaveTextContent('화면을 불러오는 중')
  expect(screen.getByRole('navigation', { name: '주요 탐색' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '프로젝트', exact: true }))
  await screen.findByRole('heading', { name: '프로젝트 화면' })
  await act(async () => pending.openApiCall())
  expect(screen.getByRole('heading', { name: '프로젝트 화면' })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'API 호출 화면' })).not.toBeInTheDocument()
  expect(window.location.pathname).toBe('/projects')
})

it('can leave member management while its code is still loading', async () => {
  window.history.replaceState(null, '', '/projects?q=saved')
  render(<App />)
  await screen.findByRole('heading', { name: '프로젝트 화면' })
  fireEvent.click(screen.getByRole('button', { name: '멤버·감사 기록' }))
  expect(screen.getByRole('status')).toHaveTextContent('화면을 불러오는 중')
  fireEvent.click(screen.getByRole('button', { name: '프로젝트', exact: true }))
  await screen.findByRole('heading', { name: '프로젝트 화면' })
  await act(async () => pending.openMembers())
  expect(screen.getByRole('heading', { name: '프로젝트 화면' })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Workspace 멤버·감사 기록' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '멤버·감사 기록' })).toHaveAttribute('aria-pressed', 'false')
})

it('shows the existing error recovery screen when a page module cannot load', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  window.history.replaceState(null, '', '/apis?project=demo')
  render(<App />)
  await screen.findByRole('heading', { name: '화면을 표시할 수 없습니다.' })
  expect(screen.getByText('화면 파일을 다운로드하지 못했습니다.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '새로고침', exact: true })).toBeInTheDocument()
})
