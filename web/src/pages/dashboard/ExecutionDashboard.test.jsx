import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ExecutionDashboard } from './ExecutionDashboard.jsx'
import { api } from '../../utils/studio.js'

vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))

const props = {
  projects: [], projectDetails: {}, projectRef: '',
  onProjectChange: vi.fn(), onOpenCases: vi.fn(), refreshKey: 0,
}

const emptyData = {
  summary: { total: 0, passed: 0, failed: 0, error: 0, timeout: 0, successRate: null, averageDurationMs: null },
  trend: Array.from({ length: 7 }, (_, index) => ({ date: `2026-09-${String(index + 1).padStart(2, '0')}`, total: 0, passed: 0, failed: 0 })),
  items: [], total: 0, page: 1, pageSize: 20,
}

afterEach(() => vi.clearAllMocks())

describe('ExecutionDashboard states', () => {
  it('shows loading until the request resolves, then the empty states', async () => {
    let resolve
    api.mockReturnValue(new Promise(done => { resolve = done }))
    render(<ExecutionDashboard {...props} />)
    expect(screen.getByRole('status')).toHaveTextContent('불러오는 중')
    resolve(emptyData)
    expect(await screen.findByText('선택한 기간에 완료된 실행이 없습니다.')).toBeInTheDocument()
    expect(screen.getByText('조회 조건에 맞는 실행 이력이 없습니다.')).toBeInTheDocument()
  })

  it('shows an error and retries from the action', async () => {
    api.mockRejectedValueOnce(new Error('연결 실패')).mockResolvedValueOnce(emptyData)
    render(<ExecutionDashboard {...props} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('연결 실패')
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }))
    await waitFor(() => expect(api).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('선택한 기간에 완료된 실행이 없습니다.')).toBeInTheDocument()
  })
})
