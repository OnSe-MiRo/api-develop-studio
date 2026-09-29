import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { LoadTestComparison } from './LoadTestComparison.jsx'
import { useRoute } from '../../router.js'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
const base = { schemaVersion: 1, run: { id: 'base', project: 'demo', scenario: 'smoke', startedAt: '2026-09-28T00:00:00Z', environment: { os: 'linux' }, status: 'passed', appVersion: '1', commitSha: 'a' }, summary: { vusMax: 2 }, thresholds: [{ metric: 'http_req_duration', condition: 'p(95)<300', actualValue: 100, passed: true }], recommendedBaseline: null }
const candidate = { ...base, run: { ...base.run, id: 'candidate', startedAt: '2026-09-28T01:00:00Z', appVersion: '2', commitSha: 'b' }, summary: { vusMax: 4 }, recommendedBaseline: base }
const delta = (baseline, candidate) => ({ baseline, candidate, delta: baseline == null || candidate == null ? null : candidate - baseline, changePercent: baseline ? (candidate - baseline) / baseline * 100 : null })
const comparison = { baseline: 'base', candidate: 'candidate', metrics: { rps: delta(20, 24), errorRate: delta(.25, .5), p95Ms: delta(192.5, 231) }, endpoints: [{ method: 'POST', endpoint: '/orders', p95Ms: delta(195, 234), errorRate: delta(0, .1) }, { method: 'GET', endpoint: '/users', p95Ms: delta(145, 174), errorRate: delta(.1, .2) }, { method: 'GET', endpoint: '/new', p95Ms: delta(null, 10), errorRate: delta(null, 0) }, { method: 'DELETE', endpoint: '/removed', p95Ms: delta(10, null), errorRate: delta(0, null) }], conditionWarnings: ['vusMax', 'appVersion', 'commitSha'] }
const series = started => ({ aggregation: 'none', sourcePoints: 2, items: [{ bucketAt: started, rps: 20, p95Ms: 100, errorRate: .25, activeVus: 2, cpuPercent: null, memoryMb: null }, { bucketAt: new Date(Date.parse(started) + 5000).toISOString(), rps: 25, p95Ms: 120, errorRate: .5, activeVus: 4, cpuPercent: null, memoryMb: null }] })
const route = { tab: 'load-test-compare', baselineId: 'base', candidateId: 'candidate', loadFilters: { project: 'demo' } }
function mockApi(path) {
  if (path.startsWith('/api/load-tests/compare')) return Promise.resolve(comparison)
  if (path.startsWith('/api/load-tests/runs?')) return Promise.resolve({ items: [candidate, base], nextCursor: null })
  if (path.endsWith('/series?maxPoints=240')) return Promise.resolve(series(path.includes('/base/') ? base.run.startedAt : candidate.run.startedAt))
  return Promise.resolve(path.endsWith('/base') ? base : candidate)
}
function Routed() { return <LoadTestComparison route={useRoute()} refreshKey={0} /> }

describe('load-test comparison UI', () => {
  beforeEach(() => { api.mockReset(); api.mockImplementation(mockApi); window.history.replaceState(null, '', '/load-tests/compare?baseline=base&candidate=candidate&project=demo') })
  it('shows golden changes, ordered endpoint candidates, zero/new/removed, criteria and both threshold verdicts', async () => {
    render(<LoadTestComparison route={route} refreshKey={0} />)
    const table = await screen.findByRole('region', { name: '핵심 지표 변화 표 가로 스크롤' })
    expect(within(table).getByText('+38.5 ms')).toBeInTheDocument()
    expect(within(table).getAllByText('+20%')).toHaveLength(2)
    expect(within(table).getByText('+25 %p')).toBeInTheDocument()
    expect(within(table).getByText('+100%')).toBeInTheDocument()
    const endpointTable = screen.getByRole('region', { name: 'Endpoint 비교 표 가로 스크롤' })
    const endpoints = within(endpointTable).getAllByRole('rowgroup')[1].querySelectorAll('th[rowspan]')
    expect([...endpoints].map(item => item.textContent)).toEqual(['POST /orders', 'GET /users', 'GET /new신규 Endpoint', 'DELETE /removed제거 Endpoint'])
    expect(within(endpointTable).getByText('판정 불가 (기준 0)')).toBeInTheDocument()
    expect(screen.getByText(/비교 조건 다름/)).toBeInTheDocument()
    expect(screen.getByText(/데이터셋 정보는 현재 결과 형식에 없어/)).toBeInTheDocument()
    expect(screen.getAllByText('정보: 다름')).toHaveLength(2)
    expect(screen.getByText('Target 부하에서 ≤ 300 ms')).toBeInTheDocument()
    expect(screen.getAllByText('Target 부하에서 ≤ 1,000 ms', { selector: 'td' })).toHaveLength(2)
    expect(screen.getAllByText('✓ 통과')).toHaveLength(2)
    expect(await screen.findByRole('table', { name: /비교 추이 데이터 표/ })).toBeInTheDocument()
  })
  it('recognizes a recorded zero VU as present and equal in comparison conditions', async () => {
    api.mockImplementation(path => {
      if (path.endsWith('/base')) return Promise.resolve({ ...base, summary: { vusMax: 0 } })
      if (path.endsWith('/candidate')) return Promise.resolve({ ...candidate, summary: { vusMax: 0 } })
      if (path.startsWith('/api/load-tests/compare')) return Promise.resolve({ ...comparison, conditionWarnings: [] })
      return mockApi(path)
    })
    render(<LoadTestComparison route={route} refreshKey={0} />)
    const region = await screen.findByRole('region', { name: '비교 조건 표 가로 스크롤' })
    const row = within(region).getByRole('row', { name: '최대 VU 0 0 같음' })
    expect(within(row).getByText('같음')).toBeInTheDocument()
    expect(within(row).queryByText('미수집')).not.toBeInTheDocument()
  })

  it('automatically recommends the candidate predecessor and preserves URLs on changes and back', async () => {
    window.history.replaceState(null, '', '/load-tests/compare?candidate=candidate&project=demo')
    render(<Routed />)
    await screen.findByText('핵심 지표 변화')
    expect(new URLSearchParams(window.location.search).get('baseline')).toBe('base')
    fireEvent.change(screen.getByLabelText('기준 실행 ID'), { target: { value: 'candidate' } })
    fireEvent.click(screen.getByRole('button', { name: '비교 적용' }))
    expect(new URLSearchParams(window.location.search).get('baseline')).toBe('candidate')
    expect(new URLSearchParams(window.location.search).get('project')).toBe('demo')
    act(() => { window.history.replaceState(null, '', '/load-tests/compare?baseline=base&candidate=candidate&project=demo'); window.dispatchEvent(new PopStateEvent('popstate')) })
    await waitFor(() => expect(screen.getByLabelText('기준 실행 ID')).toHaveValue('base'))
  })
  it('keeps no-predecessor, API incompatibility and series failures explicit', async () => {
    api.mockImplementation(path => path.endsWith('/candidate') ? Promise.resolve({ ...candidate, recommendedBaseline: null }) : mockApi(path))
    const view = render(<LoadTestComparison route={{ ...route, baselineId: '' }} refreshKey={0} />)
    expect(await screen.findByText(/같은 프로젝트·시나리오의 이전 실행이 없습니다/)).toBeInTheDocument()
    view.unmount()
    api.mockImplementation(path => path.startsWith('/api/load-tests/compare') ? Promise.reject(new Error('Runs must have the same schema version and scenario')) : mockApi(path))
    const next = render(<LoadTestComparison route={route} refreshKey={0} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('same schema version and scenario')
    expect(screen.queryByText('핵심 지표 변화')).not.toBeInTheDocument()
    next.unmount()
    api.mockImplementation(path => path.endsWith('/series?maxPoints=240') ? Promise.reject(new Error('series failed')) : mockApi(path))
    render(<LoadTestComparison route={route} refreshKey={0} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('추이 데이터 오류')
    expect(screen.getByText('핵심 지표 변화')).toBeInTheDocument()
  })
  it('ignores stale asynchronous comparison responses after a selection change', async () => {
    let resolveOld
    api.mockImplementation(path => path.includes('baseline=base') && path.startsWith('/api/load-tests/compare') ? new Promise(resolve => { resolveOld = resolve }) : mockApi(path))
    const view = render(<LoadTestComparison route={route} refreshKey={0} />)
    await waitFor(() => expect(resolveOld).toBeTypeOf('function'))
    view.rerender(<LoadTestComparison route={{ ...route, baselineId: 'candidate' }} refreshKey={0} />)
    await screen.findByText('핵심 지표 변화')
    await act(async () => { resolveOld({ ...comparison, metrics: { p95Ms: delta(100, 9999) } }) })
    expect(screen.queryByText('9,999 ms')).not.toBeInTheDocument()
  })
  it('uses elapsed time for both runs and keyboard-focusable equivalent tables', async () => {
    render(<LoadTestComparison route={route} refreshKey={0} />)
    const table = await screen.findByRole('table', { name: /비교 추이 데이터 표/ })
    expect(within(table).getAllByText('0초')).toHaveLength(2)
    expect(within(table).getAllByText('5초')).toHaveLength(2)
    for (const region of screen.getAllByRole('region')) { expect(region).toHaveAttribute('tabindex', '0'); region.focus(); expect(region).toHaveFocus() }
    expect(api).toHaveBeenCalledWith('/api/load-tests/runs/base/series?maxPoints=240', expect.any(Object))
    expect(api).toHaveBeenCalledWith('/api/load-tests/runs/candidate/series?maxPoints=240', expect.any(Object))
  })
})
