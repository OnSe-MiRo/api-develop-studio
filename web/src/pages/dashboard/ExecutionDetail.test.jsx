import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useEffect, useState } from 'react'
import { ExecutionDetail as Detail } from './ExecutionDetail.jsx'
import { api } from '../../utils/studio.js'

function ExecutionDetail(props) {
  const [filter, setFilter] = useState('all')
  useEffect(() => { setFilter('all') }, [props.runId])
  return <Detail {...props} outcomeFilter={filter} onOutcomeFilterChange={setFilter} />
}

vi.mock('../../utils/studio.js', () => ({ api: vi.fn(), asText: value => value == null ? '' : String(value) }))
afterEach(() => { vi.clearAllMocks(); sessionStorage.clear() })
const run = { runId: 'old', status: 'failed', environment: 'qa', actor: 'local-user', appVersion: 'v1', commit: 'abc', detail: { reportAvailable: true, outcomes: [{ caseReference: 'tag/api/fail.json', status: 'failed', phase: 'teardown', assertions: [{ index: 2, passed: false }] }] }, rerunRequest: { cases: [], pipelines: ['flow.json'] } }

it('shows failure metadata and retries through the server-owned rerun endpoint', async () => {
  api.mockImplementation(url => {
    if (url === '/api/executions/old') return Promise.resolve(run)
    if (url === '/api/executions/old/rerun') return Promise.resolve({ runId: 'new', status: 'queued' })
    return Promise.resolve({ runId: 'new', status: 'passed' })
  })
  render(<ExecutionDetail runId="old" onClose={vi.fn()} />)
  expect(await screen.findByText('실패 assertion (0부터 시작): 2')).toBeInTheDocument()
  expect(screen.getByText('qa')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '실패 대상 재실행' }))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/api/executions/old/rerun', expect.objectContaining({ method: 'POST', body: '{}' })))
  expect(await screen.findByText('실행 완료')).toBeInTheDocument()
})

it('shows missing detail and prevents replay of legacy or preview runs', async () => {
  api.mockResolvedValue({ ...run, detail: null, rerunRequest: null })
  render(<ExecutionDetail runId="old" onClose={vi.fn()} />)
  expect(await screen.findByText(/상세 보고서가 수집되지/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '실패 대상 재실행' })).not.toBeInTheDocument()
})

it('displays a failed detail request and recovers on retry', async () => {
  api.mockRejectedValueOnce(new Error('조회 실패')).mockResolvedValue(run)
  render(<ExecutionDetail runId="old" onClose={vi.fn()} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('조회 실패')
  fireEvent.click(screen.getByRole('button', { name: '상세 다시 시도' }))
  expect(await screen.findByText('qa')).toBeInTheDocument()
})

it('renders stored contract metadata alongside assertion failures without changing rerun targets',async()=>{
  const digest='c'.repeat(64)
  api.mockResolvedValue({...run,detail:{reportAvailable:true,outcomes:[
    {caseId:'assertion',status:'failed',errorCategory:'assertion_failed',contract:{valid:true,issueCount:0,documentDigest:digest}},
    {caseId:'contract',status:'failed',errorCategory:'contract_failed',contract:{valid:false,issueCount:2,documentDigest:digest},assertions:[]},
    {caseId:'legacy',status:'passed',assertions:[]},
    {caseId:'malformed',status:'failed',contract:{valid:true,issueCount:0,documentDigest:'PRIVATE'},assertions:[]},
  ]}})
  render(<ExecutionDetail runId="mixed" onClose={vi.fn()} />)
  expect(await screen.findByText('OpenAPI 계약 실패')).toBeInTheDocument()
  expect(screen.getByText('OpenAPI 계약 통과')).toBeInTheDocument()
  expect(screen.getByText('OpenAPI 계약 요약 없음')).toBeInTheDocument()
  expect(screen.getByText('OpenAPI 계약 요약 확인 불가')).toBeInTheDocument()
  expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument()
  expect(screen.getByText('flow.json')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'실패 대상 재실행'})).toBeEnabled()
})

it('does not let a late previous run overwrite the selected contract summary',async()=>{
  let resolveOld
  api.mockImplementation(url=>url==='/api/executions/slow'?new Promise(resolve=>{resolveOld=resolve}):Promise.resolve({...run,rerunRequest:null,detail:{reportAvailable:true,outcomes:[{caseId:'new',status:'passed',assertions:[],contract:{valid:true,issueCount:0,documentDigest:'d'.repeat(64)}}]}}))
  const view=render(<ExecutionDetail runId="slow" onClose={vi.fn()} />)
  view.rerender(<ExecutionDetail runId="fast" onClose={vi.fn()} />)
  expect(await screen.findByText('OpenAPI 계약 통과')).toBeInTheDocument()
  resolveOld({...run,detail:{reportAvailable:true,outcomes:[{caseId:'old',status:'failed',assertions:[],contract:{valid:false,issueCount:1,documentDigest:'e'.repeat(64)}}]}})
  await waitFor(()=>expect(screen.queryByText('e'.repeat(64))).not.toBeInTheDocument())
  expect(screen.getByText('d'.repeat(64))).toBeInTheDocument()
})

it('filters outcomes without inferring missing contracts or changing rerun targets', async () => {
  const outcomes = [
    { caseId: 'success-case', status: 'passed' },
    { caseId: 'assertion-case', status: 'failed', contract: { valid: true, issueCount: 0, documentDigest: 'a'.repeat(64) } },
    { caseId: 'contract-case', status: 'failed', contract: { valid: false, issueCount: 1, documentDigest: 'a'.repeat(64) } },
    { caseId: 'error-case', status: 'error' },
    { caseId: 'timeout-case', status: 'timeout' },
    { caseId: 'cancelled-case', status: 'cancelled' },
    { caseId: 'unknown-case', status: 'unknown', contract: { valid: false, issueCount: 1, documentDigest: 'PRIVATE' } },
  ]
  api.mockImplementation(url => Promise.resolve(url.endsWith('/rerun') ? { runId: 'new', status: 'passed' } : { ...run, detail: { reportAvailable: true, outcomes } }))
  render(<ExecutionDetail runId="old" onClose={vi.fn()} />)
  const filter = await screen.findByLabelText('상세 항목 필터')
  expect(screen.getByText('수집된 상세 7개 중 7개 표시')).toBeInTheDocument()
  fireEvent.change(filter, { target: { value: 'failures' } })
  expect(screen.getByText('수집된 상세 7개 중 5개 표시')).toBeInTheDocument()
  expect(screen.queryByText('success-case')).not.toBeInTheDocument()
  expect(screen.queryByText('unknown-case')).not.toBeInTheDocument()
  for (const name of ['assertion-case', 'contract-case', 'error-case', 'timeout-case', 'cancelled-case']) expect(screen.getByText(name)).toBeInTheDocument()
  fireEvent.change(filter, { target: { value: 'contract' } })
  expect(screen.getByText('수집된 상세 7개 중 1개 표시')).toBeInTheDocument()
  expect(screen.getByText('contract-case')).toBeInTheDocument()
  expect(screen.queryByText('assertion-case')).not.toBeInTheDocument()
  expect(api.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
  expect(screen.getByText('flow.json')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '실패 대상 재실행' }))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/api/executions/old/rerun', expect.objectContaining({ method: 'POST', body: '{}' })))
  fireEvent.change(filter, { target: { value: 'all' } })
  expect(screen.getByText('unknown-case')).toBeInTheDocument()
  expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument()
})

it('shows empty filters and resets to all on a different run', async () => {
  api.mockResolvedValue({ ...run, rerunRequest: null, detail: { reportAvailable: true, outcomes: [{ caseId: 'legacy-case', status: 'passed' }] } })
  const view = render(<ExecutionDetail runId="old" onClose={vi.fn()} />)
  fireEvent.change(await screen.findByLabelText('상세 항목 필터'), { target: { value: 'contract' } })
  expect(screen.getByText('선택한 조건에 맞는 상세 항목이 없습니다.')).toBeInTheDocument()
  view.rerender(<ExecutionDetail runId="next" onClose={vi.fn()} />)
  expect(await screen.findByText('legacy-case')).toBeInTheDocument()
  expect(screen.getByLabelText('상세 항목 필터')).toHaveValue('all')
  api.mockResolvedValue({ ...run, detail: null, rerunRequest: null })
  view.rerender(<ExecutionDetail runId="empty" onClose={vi.fn()} />)
  expect(await screen.findByText('수집된 상세 항목이 없습니다.')).toBeInTheDocument()
  expect(screen.getByText('수집된 상세 0개 중 0개 표시')).toBeInTheDocument()
})
