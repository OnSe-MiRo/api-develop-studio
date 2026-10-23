import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App.jsx'
import { api } from './utils/studio.js'
vi.mock('./utils/studio.js', async importOriginal => ({ ...await importOriginal(), api: vi.fn() }))
vi.mock('./auth/AuthenticationGate.jsx', () => ({ AuthenticationGate: ({ children }) => children({ userId: 'test', workspace: { id: 'team', role: 'owner' } }, {}), SessionControls: () => null }))
vi.mock('./components/StudioShell.jsx', () => ({ StudioShell: ({ children, onNavigate }) => <><button onClick={() => onNavigate({ tab: 'dashboard' })}>대시보드 이동</button><button onClick={() => onNavigate({ tab: 'pipeline-settings', activeProject: 'sample.json' })}>파이프라인 이동</button>{children}</> }))
vi.mock('./pages/projects/ProjectList.jsx', () => ({ ProjectList: () => <p>페이지 목록</p> }))
vi.mock('./pages/dashboard/ExecutionDashboard.jsx', () => ({ ExecutionDashboard: ({ projects }) => <p>선택 목록: {projects.join(',')}</p> }))
vi.mock('./pages/cases/CaseList.jsx', () => ({ CaseList: ({ onNavigate }) => <button onClick={() => onNavigate('pipeline')}>파이프라인 목록 이동</button> }))
vi.mock('./pages/pipeline-editor/PipelineEditor.jsx', () => ({ PipelineEditor: ({ caseItems }) => <p>파이프라인 선택: {caseItems.join(',')}</p> }))
it('does not fetch all projects on the list but loads selectors when navigating to the dashboard', async () => {
  window.history.replaceState(null, '', '/projects')
  api.mockImplementation(async path => path === '/api/projects' ? { items: ['sample.json'], details: {} } : path === '/api/projects/sample.json' ? { name: 'sample' } : { items: [] })
  render(<App />)
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '대시보드 이동' }))
  await waitFor(() => expect(screen.getByText('선택 목록: sample.json')).toBeInTheDocument())
  expect(api).toHaveBeenCalledWith('/api/projects')
})

vi.mock('./pages/pipelines/PipelineList.jsx', () => ({ PipelineList: () => <p>파이프라인 페이지</p> }))
it.each(['/cases?project=sample', '/pipelines?project=sample'])('does not fetch all cases on %s but preserves full pipeline selections', async (url) => {
  api.mockClear()
  window.history.replaceState(null, '', url)
  api.mockImplementation(async path => path === '/api/projects' ? { items: ['sample.json'], details: {} } : path === '/api/projects/sample.json' ? { name: 'sample' } : path.startsWith('/api/cases?') ? { items: ['tag/api/off-page.json'] } : { items: [] })
  render(<App />)
  await waitFor(() => expect(api).toHaveBeenCalledWith('/api/projects/sample.json'))
  expect(api.mock.calls.some(([url]) => url.startsWith('/api/cases'))).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '파이프라인 이동' }))
  await screen.findByText('파이프라인 선택: tag/api/off-page.json')
})

it('keeps the URL project when navigating before project metadata finishes loading', async () => {
  api.mockClear()
  window.history.replaceState(null, '', '/cases?project=sample')
  api.mockImplementation(() => new Promise(() => {}))
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '파이프라인 목록 이동' }))
  expect(window.location.pathname).toBe('/pipelines')
  expect(new URLSearchParams(window.location.search).get('project')).toBe('sample')
})
