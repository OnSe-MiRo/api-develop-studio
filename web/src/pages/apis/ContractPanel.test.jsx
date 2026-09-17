import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ContractPanel } from './ContractPanel.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
afterEach(() => vi.clearAllMocks())
it('compares selected revision and shows blocking changes', async () => {
  api.mockResolvedValueOnce({ items: [{ revision: 2 }, { revision: 1 }] }).mockResolvedValueOnce({ compatible: false, currentRevision: 2, baselineRevision: 1, issues: [], changes: [{ id: 'a', code: 'operation_removed', path: '#/paths/~1items/get', severity: 'breaking' }] })
  render(<ContractPanel projectRef="test.json" project={{ _storage: { revision: 2 } }} />)
  await screen.findByRole('option', { name: 'revision 1' })
  fireEvent.change(screen.getByLabelText('비교 기준 revision'), { target: { value: '1' } })
  fireEvent.click(screen.getByRole('button', { name: '계약 검사' }))
  expect(await screen.findByText('계약 검사 차단')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('operation_removed')
  expect(JSON.parse(api.mock.calls[1][1].body)).toEqual({ baselineRevision: 1 })
})
it('discards a previous project result that arrives late', async () => {
  let finish
  api.mockResolvedValueOnce({ items: [] }).mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValueOnce({ items: [] })
  const view = render(<ContractPanel projectRef="old.json" project={{ _storage: { revision: 1 } }} />)
  await waitFor(() => expect(api).toHaveBeenCalledTimes(1))
  fireEvent.click(screen.getByRole('button', { name: '계약 검사' }))
  view.rerender(<ContractPanel projectRef="new.json" project={{ _storage: { revision: 1 } }} />)
  finish({ compatible: false, issues: [], changes: [] })
  await waitFor(() => expect(screen.getByRole('button', { name: '계약 검사' })).toBeEnabled())
  expect(screen.queryByText('계약 검사 차단')).not.toBeInTheDocument()
})
