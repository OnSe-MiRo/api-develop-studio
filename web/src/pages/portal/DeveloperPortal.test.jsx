import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { DeveloperPortal } from './DeveloperPortal.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
vi.mock('../../components/ProjectSidebar.jsx', () => ({ AuthorSidebar: () => <aside>프로젝트</aside> }))
const release = { id: 'release-1', version: '1.0.0', projectRevision: 7, sourceDigest: 'a'.repeat(64), state: 'published', notes: 'Frozen notes', comparison: { operationChanges: [] } }
const data = { release, environments: [{ name: '환경: dev', url: 'https://dev.example.test' }], artifacts: [], permissions: { generateSdk: false }, document: { info: { title: 'Frozen API' }, security: [{ bearer: [] }], components: { securitySchemes: { bearer: { type: 'http', scheme: 'bearer' } } }, paths: { '/items': { get: { summary: 'List items', responses: { 200: { description: 'ok', content: { 'application/json': { example: { id: 7 } } } } } } }, '/old': { delete: { deprecated: true, responses: { 204: { description: 'removed' } } } } } } }
const props = { projectRef: 'demo.json', releaseId: 'release-1', onSelectRelease: vi.fn() }
beforeEach(() => { api.mockReset(); sessionStorage.clear(); props.onSelectRelease.mockReset() })
it('shows frozen revision, auth, environment and response example then searches operations', async () => {
  api.mockImplementation(async path => path.endsWith('/portal') ? { items: [release], nextCursor: null } : data)
  render(<DeveloperPortal {...props} />)
  expect(await screen.findByText('Frozen API · 1.0.0')).toBeInTheDocument()
  expect(screen.getByText('명세 revision 7')).toBeInTheDocument()
  expect(screen.getByText('bearer', { exact: true })).toBeInTheDocument()
  expect(screen.getByText(/"id": 7/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '이 릴리스로 SDK 생성' })).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('API 검색어'), { target: { value: 'DELETE old' } })
  expect(screen.getByRole('heading', { name: 'DELETE /old' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('API 검색어'), { target: { value: 'not-found' } })
  expect(screen.getByText('일치하는 API가 없습니다.')).toBeInTheDocument()
})
it('loads only the pinned release ID and does not automatically generate SDKs', async () => {
  api.mockImplementation(async path => path.endsWith('/portal') ? { items: [release], nextCursor: null } : { ...data, permissions: { generateSdk: true } })
  render(<DeveloperPortal {...props} />)
  await screen.findByRole('button', { name: '이 릴리스로 SDK 생성' })
  expect(api.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  expect(api.mock.calls.some(([path]) => path.endsWith('/portal/release-1'))).toBe(true)
})
it('keeps the selected SDK language on remount', async () => {
  api.mockImplementation(async path => path.endsWith('/portal') ? { items: [release], nextCursor: null } : data)
  const first = render(<DeveloperPortal {...props} />)
  fireEvent.change(await screen.findByLabelText('SDK 언어'), { target: { value: 'go' } })
  first.unmount()
  render(<DeveloperPortal {...props} />)
  await waitFor(() => expect(screen.getByLabelText('SDK 언어')).toHaveValue('go'))
})
it('never downloads a retained SDK without a click', async () => {
  const fetch = vi.spyOn(globalThis, 'fetch')
  api.mockImplementation(async path => path.endsWith('/portal') ? { items: [release], nextCursor: null } : { ...data, artifacts: [{ language: 'python', filename: 'sdk.zip', sizeBytes: 123, sourceDigest: release.sourceDigest, sha256: 'b'.repeat(64), generatorVersion: '7.24.0' }] })
  render(<DeveloperPortal {...props} />)
  await screen.findByRole('button', { name: '보존된 SDK ZIP 다운로드' })
  expect(fetch).not.toHaveBeenCalled()
  fetch.mockRestore()
})
