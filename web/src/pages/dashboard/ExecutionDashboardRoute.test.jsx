import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ExecutionDashboard } from './ExecutionDashboard.jsx'
import { navigateTo, useRoute } from '../../router.js'
import { api } from '../../utils/studio.js'

vi.mock('../../utils/studio.js', () => ({ api: vi.fn(), asText: value => value == null ? '' : String(value) }))

function RoutedDashboard() {
  const route = useRoute()
  return <ExecutionDashboard route={route} onNavigate={navigateTo} projectRef={route.activeProject || ''}
    projects={['demo.json', 'other.json']} projectDetails={{}} onOpenCases={() => {}} refreshKey={0} />
}

const detail = runId => ({ runId, status: 'failed', environment: 'qa', actor: 'local-user',
  detail: { reportAvailable: true, outcomes: [] }, rerunRequest: null })
const listing = (page = 1, runId = `run-${page}`) => ({
  summary: { total: 60, passed: 30, failed: 30, error: 0, timeout: 0, successRate: 50, averageDurationMs: 20 },
  trend: [], total: 60, page, pageSize: 20,
  items: [{ runId, status: 'failed', startedAt: '2026-10-28T00:00:00Z', durationMs: 20, exitCode: 1,
    targets: [{ kind: 'case', reference: 'tag/api/case.json' }], projects: ['demo.json'] }],
})
const query = () => new URLSearchParams(window.location.search)
const listQueries = () => api.mock.calls.filter(([path]) => path.startsWith('/api/dashboard?'))
  .map(([path]) => new URL(path, 'http://localhost').searchParams)
const visit = url => {
  window.history.replaceState(null, '', url)
  fireEvent(window, new PopStateEvent('popstate'))
}

beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  window.history.replaceState(null, '', '/dashboard')
  api.mockImplementation(async path => path.startsWith('/api/dashboard?')
    ? listing(Number(new URL(path, 'http://localhost').searchParams.get('page')) || 1)
    : detail(decodeURIComponent(path.split('/').pop())))
})
afterEach(() => sessionStorage.clear())

it('restores filters and a selected detail from a direct URL and after remount', async () => {
  window.history.replaceState(null, '', '/dashboard?project=demo&days=30&status=failed&page=2&search=foo&run=old')
  const view = render(<RoutedDashboard />)
  await screen.findByRole('button', { name: '실행 상세 run-2' })
  await screen.findByRole('region', { name: '실행 상세', exact: true })
  expect(screen.getByLabelText('프로젝트')).toHaveValue('demo.json')
  expect(screen.getByLabelText('조회 기간')).toHaveValue('30')
  expect(screen.getByLabelText('실행 결과')).toHaveValue('failed')
  expect(screen.getByLabelText('Run ID·실행 대상 검색')).toHaveValue('foo')
  expect(Object.fromEntries(listQueries()[0])).toMatchObject({ project: 'demo.json', days: '30', status: 'failed', page: '2', search: 'foo' })
  expect(api).toHaveBeenCalledWith('/api/executions/old', expect.any(Object))
  expect(api.mock.calls.some(([, options]) => options?.method?.toUpperCase() === 'POST')).toBe(false)
  view.unmount()
  render(<RoutedDashboard />)
  await screen.findByRole('button', { name: '실행 상세 run-2' })
  expect(screen.getByLabelText('Run ID·실행 대상 검색')).toHaveValue('foo')
  expect(api.mock.calls.filter(([path]) => path === '/api/executions/old')).toHaveLength(2)
  expect(api.mock.calls.some(([, options]) => options?.method?.toUpperCase() === 'POST')).toBe(false)
})

it('opens and closes details without losing list filters, and records page movement', async () => {
  window.history.replaceState(null, '', '/dashboard?project=demo&days=30&status=failed&page=2&search=foo')
  render(<RoutedDashboard />)
  fireEvent.click(await screen.findByRole('button', { name: '실행 상세 run-2' }))
  await screen.findByRole('region', { name: '실행 상세', exact: true })
  expect(Object.fromEntries(query())).toMatchObject({ project: 'demo', days: '30', status: 'failed', page: '2', search: 'foo', run: 'run-2' })
  fireEvent.click(screen.getByRole('button', { name: '상세 닫기' }))
  await waitFor(() => expect(screen.queryByRole('region', { name: '실행 상세', exact: true })).not.toBeInTheDocument())
  expect(query().get('run')).toBeNull()
  expect(query().get('page')).toBe('2')
  expect(query().get('search')).toBe('foo')
  fireEvent.click(screen.getByRole('button', { name: '다음', exact: true }))
  await screen.findByRole('button', { name: '실행 상세 run-3' })
  expect(query().get('page')).toBe('3')
  fireEvent.click(screen.getByRole('button', { name: '이전', exact: true }))
  await screen.findByRole('button', { name: '실행 상세 run-2' })
  expect(query().get('page')).toBe('2')
})

it('resets the page and detail when query controls change, and restores controls on popstate', async () => {
  window.history.replaceState(null, '', '/dashboard?project=demo&days=30&status=failed&page=2&search=foo&run=old')
  render(<RoutedDashboard />)
  await screen.findByRole('button', { name: '실행 상세 run-2' })
  fireEvent.change(screen.getByLabelText('조회 기간'), { target: { value: '90' } })
  await screen.findByRole('button', { name: '실행 상세 run-1' })
  expect(listQueries().at(-1).get('page')).toBe('1')
  expect(query().get('run')).toBeNull()
  fireEvent.change(screen.getByLabelText('실행 결과'), { target: { value: 'passed' } })
  await waitFor(() => expect(listQueries().at(-1).get('status')).toBe('passed'))
  fireEvent.change(screen.getByLabelText('Run ID·실행 대상 검색'), { target: { value: '  한글 검색  ' } })
  fireEvent.click(screen.getByRole('button', { name: '검색', exact: true }))
  await waitFor(() => expect(listQueries().at(-1).get('search')).toBe('한글 검색'))
  fireEvent.change(screen.getByLabelText('프로젝트'), { target: { value: 'other.json' } })
  await waitFor(() => expect(listQueries().at(-1).get('project')).toBe('other.json'))
  expect(query().get('run')).toBeNull()
  visit('/dashboard?project=demo&days=30&status=failed&page=2&search=foo&run=old')
  await screen.findByRole('button', { name: '실행 상세 run-2' })
  expect(screen.getByLabelText('프로젝트')).toHaveValue('demo.json')
  expect(screen.getByLabelText('조회 기간')).toHaveValue('30')
  expect(screen.getByLabelText('실행 결과')).toHaveValue('failed')
  expect(screen.getByLabelText('Run ID·실행 대상 검색')).toHaveValue('foo')
  expect(query().get('run')).toBe('old')
})

it('does not let a late previous list response overwrite the current URL query', async () => {
  let resolveOld
  let oldSignal
  api.mockImplementation((path, options) => {
    if (path.startsWith('/api/dashboard?')) {
      const filters = new URL(path, 'http://localhost').searchParams
      if (filters.get('search') === 'slow') {
        oldSignal = options.signal
        return new Promise(resolve => { resolveOld = resolve })
      }
      return Promise.resolve(listing(1, 'current'))
    }
    return Promise.resolve(detail('unused'))
  })
  window.history.replaceState(null, '', '/dashboard?search=slow')
  render(<RoutedDashboard />)
  fireEvent.change(screen.getByLabelText('Run ID·실행 대상 검색'), { target: { value: 'current' } })
  fireEvent.click(screen.getByRole('button', { name: '검색', exact: true }))
  await screen.findByRole('button', { name: '실행 상세 current' })
  expect(oldSignal.aborted).toBe(true)
  await act(async () => resolveOld(listing(1, 'stale')))
  expect(screen.queryByRole('button', { name: '실행 상세 stale' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '실행 상세 current' })).toBeInTheDocument()
  expect(query().get('search')).toBe('current')
})

it('keeps list filters when a missing detail is closed', async () => {
  api.mockImplementation(async path => {
    if (path === '/api/executions/missing') throw new Error('실행을 찾을 수 없습니다.')
    return listing(2)
  })
  window.history.replaceState(null, '', '/dashboard?project=demo&days=30&page=2&search=foo&run=missing')
  render(<RoutedDashboard />)
  expect(await screen.findByRole('alert')).toHaveTextContent('실행을 찾을 수 없습니다.')
  fireEvent.click(screen.getByRole('button', { name: '상세 닫기' }))
  await waitFor(() => expect(query().get('run')).toBeNull())
  expect(query().get('page')).toBe('2')
  expect(query().get('search')).toBe('foo')
})

it('restores detail filters without fetching or submitting again on filter changes', async () => {
  api.mockImplementation(async path => path.startsWith('/api/dashboard?') ? listing(2) : {
    ...detail('old'), detail: { reportAvailable: true, outcomes: [
      { caseId: 'passed-item', status: 'passed' },
      { caseId: 'assertion-item', status: 'failed' },
      { caseId: 'contract-item', status: 'failed', contract: { valid: false, issueCount: 1, documentDigest: 'a'.repeat(64) } },
    ] },
  })
  const direct = '/dashboard?project=demo&days=30&page=2&search=foo&run=old&outcomes=contract'
  window.history.replaceState(null, '', direct)
  const view = render(<RoutedDashboard />)
  expect(await screen.findByLabelText('상세 항목 필터')).toHaveValue('contract')
  expect(screen.getByText('contract-item')).toBeInTheDocument()
  expect(screen.queryByText('assertion-item')).not.toBeInTheDocument()
  view.unmount()
  render(<RoutedDashboard />)
  expect(await screen.findByLabelText('상세 항목 필터')).toHaveValue('contract')
  const callsBefore = api.mock.calls.length
  fireEvent.change(screen.getByLabelText('상세 항목 필터'), { target: { value: 'failures' } })
  expect(Object.fromEntries(query())).toMatchObject({ project: 'demo', days: '30', page: '2', search: 'foo', run: 'old', outcomes: 'failures' })
  expect(screen.getByText('assertion-item')).toBeInTheDocument()
  expect(api.mock.calls).toHaveLength(callsBefore)
  visit(direct)
  expect(screen.getByLabelText('상세 항목 필터')).toHaveValue('contract')
  expect(screen.queryByText('assertion-item')).not.toBeInTheDocument()
  visit(direct.replace('outcomes=contract', 'outcomes=failures'))
  expect(screen.getByLabelText('상세 항목 필터')).toHaveValue('failures')
  fireEvent.change(screen.getByLabelText('상세 항목 필터'), { target: { value: 'all' } })
  expect(query().has('outcomes')).toBe(false)
  fireEvent.change(screen.getByLabelText('상세 항목 필터'), { target: { value: 'contract' } })
  fireEvent.click(screen.getByRole('button', { name: '실행 상세 run-2' }))
  expect(await screen.findByLabelText('상세 항목 필터')).toHaveValue('all')
  expect(query().has('outcomes')).toBe(false)
  fireEvent.change(screen.getByLabelText('상세 항목 필터'), { target: { value: 'failures' } })
  fireEvent.click(screen.getByRole('button', { name: '상세 닫기' }))
  expect(query().has('run')).toBe(false)
  expect(query().has('outcomes')).toBe(false)
  expect(query().get('page')).toBe('2')
  visit(direct)
  await screen.findByLabelText('상세 항목 필터')
  fireEvent.change(screen.getByLabelText('조회 기간'), { target: { value: '90' } })
  expect(query().has('run')).toBe(false)
  expect(query().has('outcomes')).toBe(false)
  expect(api.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
})

it('restores case search with filters and preserves it until the selected detail changes', async () => {
  api.mockImplementation(async path => path.startsWith('/api/dashboard?') ? listing(2) : {
    ...detail('old'), detail: { reportAvailable: true, outcomes: [
      { caseId: '한글/ORDER+1', status: 'failed' }, { caseId: 'other', status: 'failed' },
    ] },
  })
  const direct = '/dashboard?days=30&page=2&run=old&outcomes=failures&caseSearch=' + encodeURIComponent('한글/order+')
  window.history.replaceState(null, '', direct)
  const view = render(<RoutedDashboard />)
  expect(await screen.findByLabelText('상세 케이스 이름·경로 검색')).toHaveValue('한글/order+')
  expect(screen.getByText('한글/ORDER+1')).toBeInTheDocument()
  expect(screen.queryByText('other')).not.toBeInTheDocument()
  view.unmount()
  render(<RoutedDashboard />)
  const input = await screen.findByLabelText('상세 케이스 이름·경로 검색')
  expect(input).toHaveValue('한글/order+')
  const calls = api.mock.calls.length
  fireEvent.change(input, { target: { value: 'other' } })
  fireEvent.submit(input.closest('form'))
  expect(query().get('caseSearch')).toBe('other')
  expect(query().get('page')).toBe('2')
  expect(query().get('outcomes')).toBe('failures')
  expect(screen.queryByText('한글/ORDER+1')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('상세 항목 필터'), { target: { value: 'all' } })
  expect(query().get('caseSearch')).toBe('other')
  visit(direct)
  expect(screen.getByLabelText('상세 케이스 이름·경로 검색')).toHaveValue('한글/order+')
  expect(screen.queryByText('other')).not.toBeInTheDocument()
  expect(api.mock.calls).toHaveLength(calls)
  fireEvent.click(screen.getByRole('button', { name: '상세 검색 초기화' }))
  expect(query().has('caseSearch')).toBe(false)
  expect(query().get('outcomes')).toBe('failures')
  visit(direct)
  fireEvent.click(await screen.findByRole('button', { name: '실행 상세 run-2' }))
  expect(await screen.findByLabelText('상세 케이스 이름·경로 검색')).toHaveValue('')
  expect(query().has('caseSearch')).toBe(false)
  visit(direct)
  await screen.findByLabelText('상세 케이스 이름·경로 검색')
  fireEvent.click(screen.getByRole('button', { name: '상세 닫기' }))
  expect(query().has('caseSearch')).toBe(false)
  expect(api.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
})
