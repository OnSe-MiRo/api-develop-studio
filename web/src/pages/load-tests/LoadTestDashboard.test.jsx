import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { LoadTestDashboard } from './LoadTestDashboard.jsx'
import { api } from '../../utils/studio.js'

vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))

const first = { run: { id: 'run-1', project: 'demo', scenario: 'target', status: 'failed', startedAt: '2026-09-27T00:00:00Z', appVersion: '1.0.1' }, summary: { requests: 100, rps: 20, vusMax: 5, errorRate: .02, latencyMs: { p50: 20, p95: 95, p99: 110 }, thresholdsPassed: false } }
const second = { run: { ...first.run, id: 'run-0', startedAt: '2026-09-26T00:00:00Z' }, summary: { ...first.summary, errorRate: .01, latencyMs: { p95: 90 } } }
const listRoute = { tab: 'load-tests', loadFilters: { project: 'demo', scenario: '', status: '', from: '', to: '', cursor: '' } }

describe('load-test dashboard', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/load-tests')
    api.mockReset()
    api.mockResolvedValue({ items: [first], nextCursor: null })
  })

  it('queries with raw project reference, displays metrics, and navigates with filters', async () => {
    api.mockImplementation(path => Promise.resolve(path.includes('scenario=target') ? { items: [first, second], nextCursor: null } : { items: [first], nextCursor: 'next-page' }))
    render(<LoadTestDashboard route={listRoute} projects={[]} projectDetails={{}} refreshKey={0} />)
    expect(await screen.findByText('최근 같은 시나리오 변화')).toBeInTheDocument()
    expect(screen.getByText('+5 ms')).toBeInTheDocument()
    expect(screen.getByText('+1%p')).toBeInTheDocument()
    expect(api).toHaveBeenCalledWith(expect.stringContaining('project=demo'), expect.any(Object))
    fireEvent.click(screen.getByRole('button', { name: /2026.*target/ }))
    expect(window.location.pathname).toBe('/load-tests/results')
    expect(new URLSearchParams(window.location.search).get('run')).toBe('run-1')
    expect(new URLSearchParams(window.location.search).get('project')).toBe('demo')
  })

  it('puts applied filters and the keyset cursor in the URL', async () => {
    api.mockResolvedValue({ items: [first], nextCursor: 'cursor+1' })
    render(<LoadTestDashboard route={listRoute} projects={[]} projectDetails={{}} refreshKey={0} />)
    await screen.findByText('실행 목록')
    fireEvent.change(screen.getByLabelText('시나리오'), { target: { value: 'smoke' } })
    fireEvent.change(screen.getByLabelText('상태'), { target: { value: 'passed' } })
    fireEvent.click(screen.getByRole('button', { name: '조회' }))
    expect(new URLSearchParams(window.location.search).get('scenario')).toBe('smoke')
    expect(new URLSearchParams(window.location.search).get('status')).toBe('passed')
  })

  it('shows empty and request-error states without hiding the filters', async () => {
    api.mockResolvedValueOnce({ items: [], nextCursor: null })
    const view = render(<LoadTestDashboard route={listRoute} projects={[]} projectDetails={{}} refreshKey={0} />)
    expect(await screen.findByText('조회 조건에 맞는 결과가 없습니다.')).toBeInTheDocument()
    view.unmount()
    api.mockRejectedValueOnce(new Error('목록 조회 실패'))
    render(<LoadTestDashboard route={listRoute} projects={[]} projectDetails={{}} refreshKey={0} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('목록 조회 실패')
    expect(screen.getByLabelText('프로젝트')).toBeInTheDocument()
  })

  it('shows a partial detail when the series request fails', async () => {
    api.mockImplementation(path => path.endsWith('/series?maxPoints=240') ? Promise.reject(new Error('추이 조회 실패')) : Promise.resolve({ ...first, run: { ...first.run, environment: { os: 'linux', cpu: '4 vCPU', memoryMb: 8192 } }, thresholds: [{ metric: 'http_req_duration', condition: 'p(95)<90', actualValue: 95, passed: false }], endpointMetrics: [{ method: 'GET', endpoint: '/users/{id}', requestCount: 100, latencyMs: { p95: 95, p99: 110 }, errorRate: .02 }], warnings: ['가져오기 경고'] }))
    render(<LoadTestDashboard route={{ tab: 'load-test-result', runId: 'run-1', loadFilters: listRoute.loadFilters }} refreshKey={0} />)
    expect(await screen.findByText('실행 환경')).toBeInTheDocument()
    expect(screen.getByText('가져오기 경고', { selector: 'li' })).toBeInTheDocument()
    expect(screen.getByText('✕ 실패')).toBeInTheDocument()
    expect(screen.getByText('/users/{id}')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('추이 데이터 오류'))
  })

  it('provides a data table equivalent for reduced time-series charts', async () => {
    api.mockImplementation(path => path.endsWith('/series?maxPoints=240') ? Promise.resolve({ aggregation: 'mean-values-peak-p95', sourcePoints: 500, items: [{ bucketAt: '2026-09-27T00:00:00Z', rps: 20, p95Ms: 95, errorRate: .02, activeVus: 5, cpuPercent: null, memoryMb: null }] }) : Promise.resolve({ ...first, run: { ...first.run, environment: {} }, thresholds: [], endpointMetrics: [], warnings: [] }))
    render(<LoadTestDashboard route={{ tab: 'load-test-result', runId: 'run-1', loadFilters: {} }} refreshKey={0} />)
    expect(await screen.findByText(/차트는 500개 구간을 축소했습니다/)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: /시간 추이 데이터 표/ })).toBeInTheDocument()
    expect(screen.getByText(/전체 요청의 재계산 percentile이 아닙니다/)).toBeInTheDocument()
  })

  it('makes detail table scroll regions reachable by keyboard focus', async () => {
    api.mockImplementation(path => path.endsWith('/series?maxPoints=240') ? Promise.resolve({ aggregation: 'none', sourcePoints: 1, items: [{ bucketAt: '2026-09-27T00:00:00Z', rps: 20, p95Ms: 95, errorRate: .02, activeVus: 5, cpuPercent: null, memoryMb: null }] }) : Promise.resolve({ ...first, thresholds: [{ metric: 'http_req_duration', condition: 'p(95)<90', actualValue: 95, passed: false }], endpointMetrics: [{ method: 'GET', endpoint: '/users/{id}', requestCount: 100, latencyMs: { p95: 95, p99: 110 }, errorRate: .02 }], warnings: [] }))
    render(<LoadTestDashboard route={{ tab: 'load-test-result', runId: 'run-1', loadFilters: {} }} refreshKey={0} />)
    const trend = await screen.findByRole('region', { name: '시간 추이 데이터 표 가로 스크롤' })
    const regions = [trend, screen.getByRole('region', { name: 'Threshold 표 가로 스크롤' }), screen.getByRole('region', { name: 'Endpoint 집계 표 가로 스크롤' })]
    for (const region of regions) {
      expect(region).toHaveAttribute('tabindex', '0')
      region.focus()
      expect(region).toHaveFocus()
    }
  })
})
