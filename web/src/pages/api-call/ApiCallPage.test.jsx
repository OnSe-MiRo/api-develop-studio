import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ApiCallPage } from './ApiCallPage.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
beforeEach(() => {
  api.mockImplementation(async url => {
    if (url === '/api/projects') return { items: ['sample.json'] }
    if (url === '/api/projects/sample.json') return { environments: { dev: { base_url: 'https://dev.example' } }, auth_profiles: { login: { type: 'Bearer Token', token: '{{project.token}}' } } }
    if (url === '/api/cases') return { items: [] }
    return {}
  })
})
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })
it('runs a selected environment and saves the same request with a profile reference', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 200, elapsedMs: 1, sizeBytes: 2, body: {}, headers: {} }) })
  vi.stubGlobal('fetch', fetch)
  render(<ApiCallPage />)
  await screen.findByRole('option', { name: 'sample.json' })
  fireEvent.change(screen.getByLabelText('소유권 확인 프로젝트'), { target: { value: 'sample.json' } })
  await screen.findByRole('option', { name: 'dev' })
  fireEvent.change(screen.getByLabelText('실행 환경'), { target: { value: 'dev' } })
  fireEvent.change(screen.getByLabelText('공통 인증 프로필'), { target: { value: 'login' } })
  fireEvent.change(screen.getByLabelText('Request URL'), { target: { value: '/echo' } })
  fireEvent.click(screen.getByRole('button', { name: '실행' }))
  await screen.findByText('200')
  const sent = JSON.parse(fetch.mock.calls[0][1].body)
  expect(sent).toMatchObject({ environment: 'dev', auth_profile: 'login', url: '/echo' })
  fireEvent.change(screen.getByLabelText('새 케이스 경로'), { target: { value: 'tag/echo/sample.json' } })
  fireEvent.click(screen.getByRole('button', { name: '현재 요청을 새 케이스로 저장' }))
  await screen.findByText(/케이스 저장 완료/)
  const saved = JSON.parse(api.mock.calls.find(([, options]) => options?.method === 'PUT')[1].body)
  expect(saved.environment).toBeUndefined()
  expect(saved.request).toMatchObject({ url: sent.url, method: sent.method, auth_profile: sent.auth_profile, headers: sent.headers })
})
it('cancels response waiting and enables rerun', async () => {
  vi.stubGlobal('fetch', vi.fn((url, options) => new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))))
  render(<ApiCallPage />)
  fireEvent.change(screen.getByLabelText('Request URL'), { target: { value: 'https://example.test' } })
  fireEvent.click(screen.getByRole('button', { name: '실행' }))
  fireEvent.click(screen.getByRole('button', { name: '응답 대기 취소' }))
  await screen.findByText(/응답 대기를 취소했습니다/)
  expect(screen.getByRole('button', { name: '실행' })).toBeEnabled()
})

it('opts into contract validation and displays failed rules without hiding the response', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 200, elapsedMs: 1, sizeBytes: 2, body: {}, headers: {}, contract: { valid: false, issues: [{ code: 'schema_required', path: '#/response/body' }] } }) })
  vi.stubGlobal('fetch', fetch)
  render(<ApiCallPage />)
  await screen.findByRole('option', { name: 'sample.json' })
  fireEvent.change(screen.getByLabelText('소유권 확인 프로젝트'), { target: { value: 'sample.json' } })
  fireEvent.click(screen.getByLabelText('OpenAPI 실제 응답 검증'))
  fireEvent.change(screen.getByLabelText('Request URL'), { target: { value: '/items' } })
  fireEvent.click(screen.getByRole('button', { name: '실행' }))
  expect(await screen.findByText('응답 계약 검증 실패')).toBeInTheDocument()
  expect(screen.getByText('200')).toBeInTheDocument()
  expect(JSON.parse(fetch.mock.calls[0][1].body).validateContract).toBe(true)
})
