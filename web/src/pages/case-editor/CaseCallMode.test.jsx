import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { CaseEditor } from './CaseEditor.jsx'
import { api } from '../../utils/studio.js'
const { start } = vi.hoisted(() => ({ start: vi.fn() }))
vi.mock('../../utils/studio.js', async original => ({ ...await original(), api: vi.fn() }))
vi.mock('../../hooks/useRunJob.js', () => ({ useRunJob: () => ({ result: null, setResult: vi.fn(), busy: false, start, cancel: vi.fn() }) }))
beforeEach(() => { vi.resetAllMocks(); api.mockResolvedValue({ items: [] }) })
const setup = props => render(<CaseEditor projectRef="demo.json" project={{ base_url: 'https://example.test' }} refresh={vi.fn()} {...props} />)
const run = async () => {
  fireEvent.click(screen.getByRole('button', { name: '실행', exact: true }))
  await waitFor(() => expect(start).toHaveBeenCalledTimes(1))
  return start.mock.calls[0][0].inlineCase
}
it('defaults to call only and sends a case without status/body/contract validation', async () => {
  setup()
  expect(screen.getByRole('radio', { name: /API 호출만/ })).toBeChecked()
  expect(screen.queryByLabelText('Expected status')).not.toBeInTheDocument()
  fireEvent.change(screen.getByPlaceholderText('/v1/users (선택한 Base URL 기준)'), { target: { value: '/items' } })
  const payload = await run()
  expect(payload.expected).toEqual({ strict: true, validation_modes: { call_only: true, exact_body: false, conditions: false } })
  expect(payload).not.toHaveProperty('contract_validation')
  expect(api.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(0)
})
it('saves the call-only mode and restores it without enabling validation', async () => {
  api.mockImplementation(async url => url.startsWith('/api/cases/') ? { request: { url: '/items' }, expected: { validation_modes: { call_only: true } } } : { items: [] })
  setup({ caseReference: 'tag/api/call.json' })
  await waitFor(() => expect(screen.getByLabelText('케이스 명')).toHaveValue('call'))
  expect(screen.getByRole('radio', { name: /API 호출만/ })).toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: '저장', exact: true }))
  await waitFor(() => expect(api.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(true))
  const payload = JSON.parse(api.mock.calls.find(([, options]) => options?.method === 'PUT')[1].body)
  expect(payload.expected.validation_modes.call_only).toBe(true)
})
it('keeps legacy validation and skips hidden invalid inputs after switching to call only', async () => {
  api.mockImplementation(async url => url.startsWith('/api/cases/') ? { request: { url: '/items' }, expected: { status: 201, body: { id: 1 } } } : { items: [] })
  setup({ caseReference: 'tag/api/legacy.json' })
  await waitFor(() => expect(screen.getByLabelText('Expected status')).toHaveValue('201'))
  expect(screen.getByRole('radio', { name: /응답 검증/ })).toBeChecked()
  expect((await run()).expected).toMatchObject({ status: 201, body: { id: 1 }, validation_modes: { exact_body: true } })
  start.mockClear()
  fireEvent.change(screen.getByDisplayValue(/"id": 1/), { target: { value: '{invalid' } })
  fireEvent.change(screen.getByLabelText('Expected status'), { target: { value: 'invalid' } })
  fireEvent.click(screen.getByRole('radio', { name: /API 호출만/ }))
  const callPayload = await run()
  expect(callPayload.expected).not.toHaveProperty('status')
  expect(callPayload._expectedBodyRaw).toBe('')
})
it('importing OpenAPI examples keeps call-only mode selected', async () => {
  api.mockImplementation(async url => url === '/api/docs' ? { operations: [{ id: 'items', method: 'GET', path: '/items', parameters: [], expected_status: 200, has_response_body: true, response_body: { ok: true } }] } : { items: [] })
  setup({ project: { docs_file: { name: 'spec.json', document: {} } } })
  fireEvent.click(screen.getByRole('button', { name: '프로젝트 API 문서 확장' }))
  const select = await screen.findByLabelText('문서 API 선택')
  fireEvent.change(select, { target: { value: 'items' } })
  expect(screen.getByRole('radio', { name: /API 호출만/ })).toBeChecked()
  expect((await run()).expected.validation_modes.call_only).toBe(true)
})
