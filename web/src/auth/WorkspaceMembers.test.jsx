import { fireEvent, render, screen } from '@testing-library/react'
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
