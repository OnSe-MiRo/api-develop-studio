import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ExecutionDetail } from './ExecutionDetail.jsx'
import { api } from '../../utils/studio.js'

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
