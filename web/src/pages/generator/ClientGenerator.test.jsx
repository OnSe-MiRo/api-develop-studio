import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ClientGenerator } from './ClientGenerator.jsx'
import { api } from '../../utils/studio.js'

vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
vi.mock('../../components/ProjectSidebar.jsx', () => ({ AuthorSidebar: () => <aside>프로젝트 메뉴</aside> }))

const project = { docs_file: { document: { openapi: '3.0.3' }, name: 'openapi.json' }, _storage: { revision: 7 } }
const props = { projects: ['demo.json'], projectRef: 'demo.json', project, onProjectChange: vi.fn(), onNavigate: vi.fn(), onProjectList: vi.fn() }
const generation = (language = 'typescript', artifactReady = true) =>
  ({ project: 'demo.json', language, projectRevision: 7, sourceDigest: 'a'.repeat(64), artifactReady })
const originalCreateObjectURL = URL.createObjectURL
const originalRevokeObjectURL = URL.revokeObjectURL

beforeEach(() => { sessionStorage.clear(); api.mockReset() })
afterEach(() => {
  if (originalCreateObjectURL) URL.createObjectURL = originalCreateObjectURL
  else delete URL.createObjectURL
  if (originalRevokeObjectURL) URL.revokeObjectURL = originalRevokeObjectURL
  else delete URL.revokeObjectURL
  vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.clearAllMocks()
})

it('submits the current revision, follows the job, and downloads only on click', async () => {
  api.mockImplementation(async path => path === '/api/generations'
    ? { runId: 'sdk-1', status: 'queued', kind: 'sdk_generation', generation: generation('typescript', false) }
    : { runId: 'sdk-1', status: 'passed', kind: 'sdk_generation', generation: generation() })
  const fetch = vi.fn().mockResolvedValue({ ok: true, headers: { get: () => 'attachment; filename="client.zip"' }, blob: async () => new Blob(['zip']) })
  vi.stubGlobal('fetch', fetch)
  URL.createObjectURL = vi.fn(() => 'blob:client')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  render(<ClientGenerator {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'SDK 생성 작업 제출' }))
  expect(await screen.findByText('생성 완료')).toBeInTheDocument()
  const submission = api.mock.calls.find(([path]) => path === '/api/generations')
  expect(JSON.parse(submission[1].body)).toEqual({ project: 'demo.json', language: 'typescript', projectRevision: 7 })
  expect(screen.getByText('요청 당시 프로젝트 revision: 7')).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'ZIP 다운로드' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/generations/sdk-1/artifact', expect.objectContaining({ signal: expect.any(AbortSignal) })))
  expect(await screen.findByText('client.zip 다운로드를 시작했습니다.')).toBeInTheDocument()
})

it('restores a completed job without resubmitting or automatically downloading and reports expired ZIP', async () => {
  sessionStorage.setItem('studio-run:sdk:demo.json:typescript', 'old-job')
  api.mockResolvedValue({ runId: 'old-job', status: 'passed', kind: 'sdk_generation', generation: generation() })
  const fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({ error: 'missing' }) })
  vi.stubGlobal('fetch', fetch)
  render(<ClientGenerator {...props} />)
  expect(await screen.findByText('생성 완료')).toBeInTheDocument()
  expect(api.mock.calls.some(([path]) => path === '/api/generations')).toBe(false)
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'ZIP 다운로드' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('만료되었거나 없습니다')
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('does not automatically retry a rejected submission', async () => {
  api.mockRejectedValue(Object.assign(new Error('생성 작업 한도 초과'), { status: 429 }))
  render(<ClientGenerator {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'SDK 생성 작업 제출' }))
  expect(await screen.findByText('생성 작업 한도 초과')).toBeInTheDocument()
  expect(api.mock.calls.filter(([path]) => path === '/api/generations')).toHaveLength(1)
  expect(api.mock.calls.some(([path]) => path.startsWith('/api/runs/'))).toBe(false)
})

it('offers cancellation while running and sends the shared job cancel request', async () => {
  api.mockImplementation(async path => {
    if (path === '/api/generations') return { runId: 'sdk-cancel', status: 'queued', kind: 'sdk_generation', generation: generation('typescript', false) }
    if (path.endsWith('/cancel')) return { runId: 'sdk-cancel', status: 'cancelled', kind: 'sdk_generation', generation: generation('typescript', false) }
    return { runId: 'sdk-cancel', status: 'running', kind: 'sdk_generation', generation: generation('typescript', false) }
  })
  render(<ClientGenerator {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'SDK 생성 작업 제출' }))
  fireEvent.click(await screen.findByRole('button', { name: '작업 취소' }))
  expect(await screen.findByText('취소됨')).toBeInTheDocument()
  expect(api).toHaveBeenCalledWith('/api/runs/sdk-cancel/cancel', { method: 'POST', body: '{}' })
})

it('keeps a late accepted job with its original language and restores it when selected again', async () => {
  let acceptPython
  api.mockImplementation((path, options) => {
    if (path === '/api/generations') return new Promise(resolve => { acceptPython = resolve })
    return Promise.resolve({ runId: 'python-job', status: 'passed', kind: 'sdk_generation', generation: generation('python') })
  })
  render(<ClientGenerator {...props} />)
  fireEvent.change(screen.getByLabelText('생성 언어'), { target: { value: 'python' } })
  fireEvent.click(screen.getByRole('button', { name: 'SDK 생성 작업 제출' }))
  fireEvent.change(screen.getByLabelText('생성 언어'), { target: { value: 'go' } })
  await act(async () => { acceptPython({ runId: 'python-job', status: 'queued', kind: 'sdk_generation', generation: generation('python', false) }) })
  expect(screen.queryByText('python-job')).not.toBeInTheDocument()
  expect(sessionStorage.getItem('studio-run:sdk:demo.json:python')).toBe('python-job')
  expect(sessionStorage.getItem('studio-run:sdk:demo.json:go')).toBeNull()
  fireEvent.change(screen.getByLabelText('생성 언어'), { target: { value: 'python' } })
  expect(await screen.findByText('생성 완료')).toBeInTheDocument()
  expect(api.mock.calls.filter(([path]) => path === '/api/generations')).toHaveLength(1)
})


it('restores the selected non-default language and its job after remount without another submission', async () => {
  api.mockImplementation(async path => ({ runId: 'go-job', status: 'passed', kind: 'sdk_generation', generation: generation('go') }))
  const first = render(<ClientGenerator {...props} />)
  fireEvent.change(screen.getByLabelText('생성 언어'), { target: { value: 'go' } })
  fireEvent.click(screen.getByRole('button', { name: 'SDK 생성 작업 제출' }))
  expect(await screen.findByText('go-job')).toBeInTheDocument()
  first.unmount()
  render(<ClientGenerator {...props} />)
  expect(screen.getByLabelText('생성 언어')).toHaveValue('go')
  expect(await screen.findByText('go-job')).toBeInTheDocument()
  expect(api.mock.calls.filter(([path]) => path === '/api/generations')).toHaveLength(1)
})

it('keeps language preferences and restored jobs isolated when switching projects', async () => {
  sessionStorage.setItem('studio-sdk-language:other.json', 'java')
  sessionStorage.setItem('studio-run:sdk:other.json:java', 'other-job')
  api.mockResolvedValue({ runId: 'other-job', status: 'passed', kind: 'sdk_generation', generation: generation('java') })
  const view = render(<ClientGenerator {...props} />)
  fireEvent.change(screen.getByLabelText('생성 언어'), { target: { value: 'go' } })
  view.rerender(<ClientGenerator {...props} projectRef="other.json" />)
  expect(screen.getByLabelText('생성 언어')).toHaveValue('java')
  expect(await screen.findByText('other-job')).toBeInTheDocument()
  view.rerender(<ClientGenerator {...props} />)
  expect(screen.getByLabelText('생성 언어')).toHaveValue('go')
  expect(screen.queryByText('other-job')).not.toBeInTheDocument()
  expect(api.mock.calls.some(([path]) => path === '/api/generations')).toBe(false)
})

it('ignores unsupported stored languages', () => {
  sessionStorage.setItem('studio-sdk-language:demo.json', 'unsupported')
  render(<ClientGenerator {...props} />)
  expect(screen.getByLabelText('생성 언어')).toHaveValue('typescript')
})
