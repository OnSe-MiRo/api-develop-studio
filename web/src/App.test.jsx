import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App.jsx'
import { api } from './utils/studio.js'
vi.mock('./utils/studio.js', async importOriginal => ({ ...await importOriginal(), api: vi.fn() }))
vi.mock('./auth/AuthenticationGate.jsx', () => ({ AuthenticationGate: ({ children }) => children({ userId: 'test', workspace: { id: 'team', role: 'owner' } }, {}), SessionControls: () => null }))
vi.mock('./components/StudioShell.jsx', () => ({ StudioShell: ({ children, onNavigate }) => <><button onClick={() => onNavigate({ tab: 'dashboard' })}>대시보드 이동</button>{children}</> }))
vi.mock('./pages/projects/ProjectList.jsx', () => ({ ProjectList: () => <p>페이지 목록</p> }))
vi.mock('./pages/dashboard/ExecutionDashboard.jsx', () => ({ ExecutionDashboard: ({ projects }) => <p>선택 목록: {projects.join(',')}</p> }))
it('does not fetch all projects on the list but loads selectors when navigating to the dashboard', async () => {
  window.history.replaceState(null, '', '/projects')
  api.mockImplementation(async path => path === '/api/projects' ? { items: ['sample.json'], details: {} } : path === '/api/projects/sample.json' ? { name: 'sample' } : { items: [] })
  render(<App />)
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '대시보드 이동' }))
  await waitFor(() => expect(screen.getByText('선택 목록: sample.json')).toBeInTheDocument())
  expect(api).toHaveBeenCalledWith('/api/projects')
})
