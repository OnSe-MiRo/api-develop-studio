import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CoveragePanel } from './CoveragePanel.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
afterEach(() => vi.clearAllMocks())
const coverage = { operations: [{ id: 'GET /items', responses: [{ status: '200', cases: [], lastSuccess: null }], cases: [{ reference: 't/a/c.json', changed: true, linked: true }] }], unlinked: [] }
it('shows missing responses and submits only selected safe fields with revisions', async () => {
  api.mockResolvedValueOnce(coverage).mockResolvedValueOnce({ changes: [{ field: 'request.url', before: '/old', after: '/new', selectable: true }, { field: 'expected.status', before: 200, after: 201, selectable: false, reason: '사용자 수정 값 보존' }], projectRevision: 2, caseRevision: 3 }).mockResolvedValueOnce({}).mockResolvedValueOnce(coverage)
  render(<CoveragePanel projectRef="p.json" revision={2} />)
  expect(await screen.findByText(/미검증 응답/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '변경 미리보기' }))
  const checkbox = await screen.findByRole('checkbox', { name: /request.url/ })
  expect(screen.getByRole('checkbox', { name: /expected.status/ })).toBeDisabled()
  fireEvent.click(checkbox)
  fireEvent.click(screen.getByRole('button', { name: '선택 필드 및 연결 기준 저장' }))
  await waitFor(() => expect(api).toHaveBeenCalledTimes(4))
  expect(JSON.parse(api.mock.calls[2][1].body)).toEqual({ case: 't/a/c.json', apply: true, fields: ['request.url'], projectRevision: 2, caseRevision: 3 })
})
it('keeps Example synchronization read only', async () => {
  api.mockResolvedValueOnce(coverage).mockResolvedValueOnce({ changes: [], projectRevision: 1, caseRevision: 1 })
  render(<CoveragePanel projectRef="example-api.json" revision={1} />)
  fireEvent.click(await screen.findByRole('button', { name: '변경 미리보기' }))
  expect(await screen.findByRole('button', { name: '선택 필드 및 연결 기준 저장' })).toBeDisabled()
})
