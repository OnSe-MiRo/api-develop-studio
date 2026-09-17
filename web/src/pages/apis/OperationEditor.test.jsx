import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { OperationEditor } from './OperationEditor.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
afterEach(() => vi.clearAllMocks())
const props = { operation: { method: 'GET', path: '/items', editable: { operationId: 'listItems', summary: 'Before' } }, projectRef: 'test.json', project: { _storage: { revision: 4 } }, onSaved: vi.fn(), onCancel: vi.fn() }
it('requires preview and sends only edited fields with the revision', async () => {
  api.mockResolvedValue({})
  render(<OperationEditor {...props} />)
  fireEvent.change(screen.getByLabelText('summary'), { target: { value: 'After' } })
  expect(screen.queryByRole('button', { name: '변경 저장' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('변경 미리보기'))
  expect(screen.getByRole('region', { name: '변경 미리보기' })).toHaveTextContent('Before')
  fireEvent.click(screen.getByText('변경 저장'))
  await waitFor(() => expect(props.onSaved).toHaveBeenCalled())
  expect(JSON.parse(api.mock.calls[0][1].body)).toEqual({ action: 'update', method: 'GET', path: '/items', changes: { summary: 'After' }, _storage: { revision: 4 } })
})
it('requires delete confirmation and retains edits on conflict', async () => {
  api.mockRejectedValue(new Error('revision conflict'))
  render(<OperationEditor {...props} />)
  fireEvent.click(screen.getByText('Operation 삭제'))
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('삭제 확정'))
  expect(await screen.findByRole('alert')).toHaveTextContent('revision conflict')
  expect(props.onSaved).not.toHaveBeenCalled()
})
