import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { OperationEditor } from './OperationEditor.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
afterEach(() => vi.clearAllMocks())
const operation = { operationId: 'listItems', summary: 'Before', 'x-existing': { value: 1 }, responses: { 200: { description: 'OK' } } }
const editor = {
  source: { kind: 'file', entrypoint: 'openapi.json', files: { 'openapi.json': { openapi: '3.0.3', paths: { '/items': { get: operation } } } } },
  catalog: { operations: [{ method: 'GET', path: '/items', file: 'openapi.json', pointer: '#/paths/~1items/get' }], schemas: [], securitySchemes: [] },
  sourceDigest: 'a'.repeat(64), _storage: { revision: 4 },
}
const props = { operation: { method: 'GET', path: '/items' }, projectRef: 'test.json', project: { _storage: { revision: 4 } }, onSaved: vi.fn(), onCancel: vi.fn() }
const preview = { issues: [], changedFiles: ['openapi.json'], affectedOperations: ['GET /items'] }
it('previews the raw owner fragment and applies the exact validated edit with revision and digest', async () => {
  api.mockImplementation((_, options) => Promise.resolve(options ? preview : editor))
  render(<OperationEditor {...props} />)
  fireEvent.change(await screen.findByLabelText('summary'), { target: { value: 'After' } })
  expect(screen.queryByRole('button', { name: '검증된 변경 저장' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '변경 미리보기·전체 검증' }))
  expect(await screen.findByRole('region', { name: '변경 미리보기' })).toHaveTextContent('openapi.json')
  fireEvent.click(screen.getByRole('button', { name: '검증된 변경 저장' }))
  await waitFor(() => expect(props.onSaved).toHaveBeenCalled())
  const request = JSON.parse(api.mock.calls[1][1].body)
  expect(request).toMatchObject({ action: 'preview', _storage: { revision: 4 }, sourceDigest: 'a'.repeat(64) })
  expect(request.edits[0]).toEqual({ file: 'openapi.json', op: 'replace', path: '#/paths/~1items/get', value: { ...operation, summary: 'After' } })
  expect(JSON.parse(api.mock.calls[2][1].body)).toEqual({ ...request, action: 'apply' })
})
it('previews deletion and keeps the draft after an apply conflict', async () => {
  api.mockImplementation((_, options) => !options ? Promise.resolve(editor) : JSON.parse(options.body).action === 'preview' ? Promise.resolve(preview) : Promise.reject(new Error('revision conflict')))
  render(<OperationEditor {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Operation 삭제' }))
  expect(api).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: '변경 미리보기·전체 검증' }))
  fireEvent.click(await screen.findByRole('button', { name: '삭제 확정' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('revision conflict')
  expect(JSON.parse(api.mock.calls[1][1].body).edits[0]).toEqual({ file: 'openapi.json', op: 'remove', path: '#/paths/~1items/get' })
  expect(props.onSaved).not.toHaveBeenCalled()
})
it('blocks preview when a raw JSON draft is invalid', async () => {
  api.mockImplementation((_, options) => Promise.resolve(options ? preview : editor))
  render(<OperationEditor {...props} />)
  const summary = await screen.findByText('Operation 고급 JSON 편집')
  fireEvent.click(summary)
  fireEvent.change(within(summary.closest('details')).getByRole('textbox'), { target: { value: '{' } })
  expect(screen.getByText('JSON 입력 오류를 수정해야 미리볼 수 있습니다.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '변경 미리보기·전체 검증' })).toBeDisabled()
  expect(api).toHaveBeenCalledTimes(1)
})
it('keeps a structurally invalid but parseable operation draft from crashing or saving', async () => {
  api.mockImplementation((_, options) => Promise.resolve(options ? preview : editor))
  render(<OperationEditor {...props} />)
  const summary = await screen.findByText('Operation 고급 JSON 편집')
  fireEvent.click(summary)
  fireEvent.change(within(summary.closest('details')).getByRole('textbox'), { target: { value: JSON.stringify({ ...operation, parameters: {}, tags: 'bad' }) } })
  expect(screen.getByText('Operation: 편집 가능한 OpenAPI 구조를 입력하세요.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '변경 미리보기·전체 검증' })).toBeDisabled()
  expect(api).toHaveBeenCalledTimes(1)
})
it('restores the selected operation after visiting component schemas', async () => {
  const data = structuredClone(editor)
  data.source.files['openapi.json'].components = { schemas: { Pet: { type: 'object' } } }
  data.catalog.schemas = [{ name: 'Pet', file: 'openapi.json', pointer: '#/components/schemas/Pet', entrypointPointer: '#/components/schemas/Pet', refByFile: { 'openapi.json': '#/components/schemas/Pet' } }]
  api.mockResolvedValue(data)
  render(<OperationEditor {...props} />)
  await screen.findByLabelText('summary')
  fireEvent.click(screen.getByRole('tab', { name: 'Component schemas' }))
  fireEvent.change(screen.getByLabelText('Schema 선택'), { target: { value: 'Pet' } })
  expect(screen.getByLabelText('Schema 선택')).toHaveValue('Pet')
  fireEvent.click(screen.getByRole('tab', { name: 'Operation' }))
  expect(screen.getByLabelText('summary')).toHaveValue('Before')
})
it('resets an invalid schema JSON draft when selecting another schema', async () => {
  const data = structuredClone(editor)
  data.source.files['openapi.json'].components = { schemas: { A: { type: 'object' }, B: { type: 'string' } } }
  data.catalog.schemas = ['A', 'B'].map(name => ({ name, file: 'openapi.json', pointer: `#/components/schemas/${name}`, entrypointPointer: `#/components/schemas/${name}` }))
  api.mockResolvedValue(data)
  render(<OperationEditor {...props} operation={null} />)
  const chooser = await screen.findByLabelText('Schema 선택')
  fireEvent.change(chooser, { target: { value: 'A' } })
  const summary = screen.getByText('Schema 고급 JSON 편집')
  fireEvent.click(summary)
  fireEvent.change(within(summary.closest('details')).getByRole('textbox'), { target: { value: '{' } })
  expect(screen.getByText('JSON 입력 오류를 수정해야 미리볼 수 있습니다.')).toBeInTheDocument()
  fireEvent.change(chooser, { target: { value: 'B' } })
  expect(screen.queryByText('JSON 입력 오류를 수정해야 미리볼 수 있습니다.')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '변경 미리보기·전체 검증' })).toBeEnabled()
})
it('keeps every scheme in an AND security requirement when editing its JSON', async () => {
  const data = structuredClone(editor)
  data.source.files['openapi.json'].paths['/items'].get.security = [{ OAuth: ['read'], ApiKey: [] }]
  data.catalog.securitySchemes = [{ name: 'OAuth' }, { name: 'ApiKey' }]
  api.mockImplementation((_, options) => Promise.resolve(options ? preview : data))
  render(<OperationEditor {...props} />)
  expect(await screen.findByText(/AND: OAuth \+ ApiKey/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Security requirements JSON'), { target: { value: '[{"OAuth":["write"],"ApiKey":[]}]' } })
  fireEvent.click(screen.getByRole('button', { name: '변경 미리보기·전체 검증' }))
  await screen.findByRole('region', { name: '변경 미리보기' })
  expect(JSON.parse(api.mock.calls[1][1].body).edits[0].value.security).toEqual([{ OAuth: ['write'], ApiKey: [] }])
})
it('deletes an external schema declaration from the entrypoint, keeping its shared owner file', async () => {
  const data = structuredClone(editor)
  data.source.kind = 'bundle'
  data.source.files['openapi.json'].components = { schemas: { Pet: { $ref: 'components/Pet.json#' } } }
  data.source.files['components/Pet.json'] = { type: 'object' }
  data.catalog.schemas = [{ name: 'Pet', file: 'components/Pet.json', pointer: '#', entrypointPointer: '#/components/schemas/Pet' }]
  api.mockImplementation((_, options) => Promise.resolve(options ? preview : data))
  render(<OperationEditor {...props} operation={null} />)
  fireEvent.change(await screen.findByLabelText('Schema 선택'), { target: { value: 'Pet' } })
  fireEvent.click(screen.getByRole('button', { name: 'Schema 삭제' }))
  fireEvent.click(screen.getByRole('button', { name: '변경 미리보기·전체 검증' }))
  await screen.findByRole('region', { name: '변경 미리보기' })
  expect(JSON.parse(api.mock.calls[1][1].body).edits[0]).toEqual({ file: 'openapi.json', op: 'remove', path: '#/components/schemas/Pet' })
})
