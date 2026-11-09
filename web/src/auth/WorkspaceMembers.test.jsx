import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { WorkspaceMembers } from './WorkspaceMembers.jsx'
import { api } from '../utils/studio.js'
vi.mock('../utils/studio.js', () => ({ api: vi.fn() }))
beforeEach(() => { api.mockReset() })
it('requires a reason and sends the selected membership fields', async () => {
  api.mockImplementation(async (path, options) => options?.method === 'POST' ? { saved: true } : path.endsWith('/members') ? { items: [{ user_id: 'bob', display_name: 'Bob', role: 'viewer', status: 'active', version: 1 }] } : { items: [], nextCursor: null })
  render(<WorkspaceMembers onClose={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Bob · viewer · active' }))
  expect(screen.getByRole('button', { name: 'membership 변경 저장' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('역할'), { target: { value: 'runner' } })
  fireEvent.change(screen.getByLabelText('변경 사유'), { target: { value: 'Approved runner' } })
  fireEvent.click(screen.getByRole('button', { name: 'membership 변경 저장' }))
  expect(JSON.parse(api.mock.calls.find(([, options]) => options?.method === 'POST')[1].body)).toEqual({ userId: 'bob', role: 'runner', status: 'active', reason: 'Approved runner', revision: 1 })
})

it('shows loading and separate empty member and audit sections', async () => {
  let resolve
  const pending = new Promise(done => { resolve = done })
  api.mockReturnValue(pending)
  const view = render(<WorkspaceMembers onClose={vi.fn()} />)
  expect(screen.getByRole('status')).toHaveTextContent('불러오는 중')
  expect(screen.queryByText('표시할 멤버가 없습니다.')).not.toBeInTheDocument()
  api.mockResolvedValue({ items: [], nextCursor: null })
  view.rerender(<WorkspaceMembers refreshKey={1} onClose={vi.fn()} />)
  expect(await screen.findByText('표시할 멤버가 없습니다.')).toBeInTheDocument()
  expect(screen.getByText('아직 감사 기록이 없습니다.')).toBeInTheDocument()
  expect(screen.getByRole('region', { name: '멤버 0' })).toBeInTheDocument()
  expect(screen.getByRole('region', { name: '감사 기록' })).toBeInTheDocument()
  await act(async () => { resolve({ items: [], nextCursor: null }) })
})

it.each(['success', 'failure'])('ignores a stale initial reload %s after a newer refresh', async outcome => {
  let resolveOld, rejectOld
  const old = new Promise((resolve, reject) => { resolveOld = resolve; rejectOld = reject })
  api.mockImplementation(() => old)
  const view = render(<WorkspaceMembers onClose={vi.fn()} />)
  api.mockImplementation(async path => path.endsWith('/members') ? { items: [{ user_id: 'new', display_name: 'Newest member', role: 'viewer', status: 'active' }] } : { items: [{ id: 'new', action: 'newest_event', detail: { reason: 'Newest detail' } }], nextCursor: null })
  view.rerender(<WorkspaceMembers refreshKey={1} onClose={vi.fn()} />)
  await screen.findByRole('button', { name: 'Newest member · viewer · active' })
  await act(async () => {
    if (outcome === 'success') resolveOld({ items: [], nextCursor: 'stale-cursor' })
    else rejectOld(new Error('Stale request failed'))
  })
  expect(screen.getByRole('button', { name: 'Newest member · viewer · active' })).toBeEnabled()
  expect(screen.getByText('newest_event')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '이전 감사 기록 더 보기' })).not.toBeInTheDocument()
  const details = screen.getByText('변경 상세').closest('details')
  expect(details).not.toHaveAttribute('open')
  fireEvent.click(screen.getByText('변경 상세'))
  expect(details).toHaveAttribute('open')
  expect(screen.getByText(/Newest detail/)).toBeVisible()
})

it('does not append an old audit page after a newer refresh', async () => {
  let resolvePage
  const page = new Promise(resolve => { resolvePage = resolve })
  let refreshed = false
  api.mockImplementation(async path => path.includes('?before=') ? page : path.endsWith('/members') ? { items: [] } : { items: [{ id: refreshed ? 'new' : 'first', action: refreshed ? 'newest_event' : 'first_event', detail: {} }], nextCursor: refreshed ? null : 'older/1' })
  const view = render(<WorkspaceMembers onClose={vi.fn()} />)
  const more = await screen.findByRole('button', { name: '이전 감사 기록 더 보기' })
  await waitFor(() => expect(more).toBeEnabled())
  fireEvent.click(more)
  expect(api).toHaveBeenCalledWith('/api/workspace/audit?before=older%2F1')
  refreshed = true
  view.rerender(<WorkspaceMembers refreshKey={1} onClose={vi.fn()} />)
  await screen.findByText('newest_event')
  await act(async () => { resolvePage({ items: [{ id: 'old', action: 'old_page_event', detail: {} }], nextCursor: 'old-cursor' }) })
  expect(screen.queryByText('old_page_event')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '이전 감사 기록 더 보기' })).not.toBeInTheDocument()
})
