import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { api } from './utils/studio.js'

vi.mock('./utils/studio.js', async importOriginal => ({ ...await importOriginal(), api: vi.fn() }))
vi.mock('./auth/AuthenticationGate.jsx', async importOriginal => ({
  ...await importOriginal(),
  AuthenticationGate: ({ children }) => children({ userId: 'test', displayName: 'Test Owner', mode: 'local', workspace: { id: 'team', role: 'owner' } }, {}),
}))
vi.mock('./pages/api-call/ApiCallPage.jsx', () => ({ ApiCallPage: () => <h1>API 호출 화면</h1> }))
vi.mock('./pages/projects/ProjectList.jsx', () => ({ ProjectList: () => <h1>프로젝트 화면</h1> }))
vi.mock('./pages/cases/CaseList.jsx', () => ({ CaseList: () => <h1>케이스 화면</h1> }))
vi.mock('./pages/dashboard/ExecutionDashboard.jsx', () => ({ ExecutionDashboard: () => <h1>대시보드 화면</h1> }))
vi.mock('./pages/load-tests/LoadTestDashboard.jsx', () => ({ LoadTestDashboard: () => <h1>부하테스트 화면</h1> }))

beforeEach(() => {
  api.mockReset()
  api.mockResolvedValue({ items: [], nextCursor: null })
})

it.each([
  ['/api-call', 'API 호출', '/api-call'],
  ['/api-call', '프로젝트', '/projects'],
  ['/projects', '프로젝트', '/projects'],
  ['/projects', 'API 호출', '/api-call'],
  ['/api-call', '대시보드', '/dashboard'],
  ['/api-call', '부하테스트', '/load-tests'],
])('leaves member management from %s when selecting %s', async (initialUrl, target, expectedUrl) => {
  window.history.replaceState(null, '', initialUrl)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '멤버·감사 기록' }))
  await screen.findByRole('heading', { name: 'Workspace 멤버·감사 기록' })
  expect(screen.getByRole('button', { name: '멤버·감사 기록' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('navigation', { name: '주요 탐색' }).querySelector('[aria-current="page"]')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: target, exact: true }))
  expect(window.location.pathname).toBe(expectedUrl)
  expect(screen.queryByRole('heading', { name: 'Workspace 멤버·감사 기록' })).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: `${target} 화면` })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: target, exact: true })).toHaveAttribute('aria-current', 'page')
})

it('leaves member management on browser history navigation', async () => {
  window.history.replaceState(null, '', '/api-call')
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '멤버·감사 기록' }))
  await screen.findByRole('heading', { name: 'Workspace 멤버·감사 기록' })
  window.history.replaceState(null, '', '/projects')
  fireEvent.popState(window)
  expect(screen.queryByRole('heading', { name: 'Workspace 멤버·감사 기록' })).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '프로젝트 화면' })).toBeInTheDocument()
})

it('keeps a member edit open when background project selection normalizes the URL', async () => {
  let resolveProjects
  const projects = new Promise(resolve => { resolveProjects = resolve })
  api.mockImplementation(async path => path === '/api/projects?page_size=1' ? projects : path === '/api/projects/sample.json' ? { name: 'Sample' } : path === '/api/workspace/members' ? { items: [{ user_id: 'bob', display_name: 'Bob', role: 'viewer', status: 'active', version: 1 }] } : { items: [], nextCursor: null })
  window.history.replaceState(null, '', '/cases')
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '멤버·감사 기록' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Bob · viewer · active' }))
  fireEvent.change(screen.getByLabelText('변경 사유'), { target: { value: 'Keep this draft' } })
  await act(async () => { resolveProjects({ items: ['sample.json'] }) })
  await waitFor(() => expect(new URLSearchParams(window.location.search).get('project')).toBe('sample'))
  expect(screen.getByRole('heading', { name: 'Workspace 멤버·감사 기록' })).toBeInTheDocument()
  expect(screen.getByLabelText('변경 사유')).toHaveValue('Keep this draft')
})

it('refreshes the visible member screen without returning to the underlying page', async () => {
  window.history.replaceState(null, '', '/api-call')
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '멤버·감사 기록' }))
  await screen.findByText('아직 감사 기록이 없습니다.')
  fireEvent.click(screen.getByRole('button', { name: '↻ 새로고침' }))
  await waitFor(() => expect(api.mock.calls.filter(([path]) => path === '/api/workspace/members')).toHaveLength(2))
  expect(api.mock.calls.filter(([path]) => path === '/api/workspace/audit')).toHaveLength(2)
  expect(screen.getByRole('heading', { name: 'Workspace 멤버·감사 기록' })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'API 호출 화면' })).not.toBeInTheDocument()
})
