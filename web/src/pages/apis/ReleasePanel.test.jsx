import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ReleasePanel } from './ReleasePanel.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
const project = { docs_file: { document: { openapi: '3.0.3' } }, _storage: { revision: 7 } }
const release = { id: 'release-one', version: '1.0.0', projectRevision: 7, sourceDigest: 'a'.repeat(64), state: 'draft', revision: 1, notes: '<script>plain text</script>', comparison: { issues: [], changes: [] }, deprecatedOperations: [{ method: 'GET', path: '/old' }], events: [{ revision: 1, to_state: 'draft', actor_id: 'local-user', reason: 'Created', created_at: '2026-10-13' }] }
beforeEach(() => { api.mockReset() })
it('creates a draft for the current revision and displays deprecated operations', async () => {
  api.mockImplementation(async (path, options) => options?.method === 'POST' ? release : { items: [], nextCursor: null })
  render(<ReleasePanel projectRef="demo.json" project={project} />)
  await screen.findByText('등록된 릴리스가 없습니다.')
  fireEvent.click(screen.getByText('릴리스 초안 만들기'))
  fireEvent.change(screen.getByLabelText('릴리스 버전'), { target: { value: '1.0.0' } })
  fireEvent.click(screen.getByRole('button', { name: '현재 revision으로 초안 생성' }))
  expect(await screen.findByText('1.0.0 · 초안')).toBeInTheDocument()
  expect(screen.getByText('/old')).toBeInTheDocument()
  expect(screen.getByText('<script>plain text</script>')).toBeInTheDocument()
  expect(JSON.parse(api.mock.calls.find(([, options]) => options?.method === 'POST')[1].body)).toMatchObject({ version: '1.0.0', projectRevision: 7 })
})
it('requires reason and explicit acknowledgement for a breaking change', async () => {
  const detail = { ...release, comparison: { issues: [], changes: [{ id: 'change', severity: 'breaking', code: 'operation_removed', path: '/old' }] } }
  api.mockImplementation(async path => path.endsWith('/release-one') ? detail : { items: [release], nextCursor: null })
  render(<ReleasePanel projectRef="demo.json" project={project} />)
  fireEvent.click(await screen.findByRole('button', { name: '1.0.0 · 초안 · 명세 revision 7' }))
  await screen.findByLabelText('승인·전환 사유')
  expect(screen.getByRole('button', { name: '릴리스 상태 변경' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('승인·전환 사유'), { target: { value: 'Reviewed migration' } })
  expect(screen.getByRole('button', { name: '릴리스 상태 변경' })).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', { name: '호환성 변경을 검토하고 승인합니다' }))
  expect(screen.getByRole('button', { name: '릴리스 상태 변경' })).toBeEnabled()
})
it('does not automatically retry a conflicting approval', async () => {
  api.mockImplementation(async path => { if (path.endsWith('/transition')) throw new Error('릴리스가 변경됐습니다.'); return path.endsWith('/release-one') ? release : { items: [release], nextCursor: null } })
  render(<ReleasePanel projectRef="demo.json" project={project} />)
  fireEvent.click(await screen.findByRole('button', { name: '1.0.0 · 초안 · 명세 revision 7' }))
  fireEvent.change(await screen.findByLabelText('승인·전환 사유'), { target: { value: 'Reviewed' } })
  fireEvent.click(screen.getByRole('button', { name: '릴리스 상태 변경' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('릴리스가 변경됐습니다.')
  expect(api.mock.calls.filter(([path]) => path.endsWith('/transition'))).toHaveLength(1)
})
it('loads the pinned source instead of the latest project document', async () => {
  api.mockImplementation(async path => path.endsWith('/source') ? { projectRevision: 7, sourceDigest: release.sourceDigest, source: { kind: 'file', document: { info: { title: 'Pinned source' } } } } : path.endsWith('/release-one') ? release : { items: [release], nextCursor: null })
  render(<ReleasePanel projectRef="demo.json" project={{ ...project, _storage: { revision: 10 } }} />)
  fireEvent.click(await screen.findByRole('button', { name: '1.0.0 · 초안 · 명세 revision 7' }))
  fireEvent.click(await screen.findByRole('button', { name: '고정된 명세 원본 보기' }))
  await waitFor(() => expect(screen.getByLabelText('고정된 명세 원본')).toHaveTextContent('Pinned source'))
})
it('disables draft creation for URL-only projects', async () => {
  api.mockResolvedValue({ items: [], nextCursor: null })
  render(<ReleasePanel projectRef="demo.json" project={{ docs_url: 'https://example.test/spec.json', _storage: { revision: 1 } }} />)
  await screen.findByText('등록된 릴리스가 없습니다.')
  fireEvent.click(screen.getByText('릴리스 초안 만들기'))
  fireEvent.change(screen.getByLabelText('릴리스 버전'), { target: { value: '1.0.0' } })
  expect(screen.getByRole('button', { name: '현재 revision으로 초안 생성' })).toBeDisabled()
})

it('clears selected source and draft fields on project change', async () => {
  api.mockImplementation(async path => path.includes('other.json') ? { items: [], nextCursor: null } : path.endsWith('/release-one') ? release : { items: [release], nextCursor: null })
  const view = render(<ReleasePanel projectRef="demo.json" project={project} />)
  fireEvent.click(await screen.findByRole('button', { name: '1.0.0 · 초안 · 명세 revision 7' }))
  await screen.findByLabelText('선택한 릴리스')
  view.rerender(<ReleasePanel projectRef="other.json" project={project} />)
  expect(screen.queryByLabelText('선택한 릴리스')).not.toBeInTheDocument()
  expect(await screen.findByText('등록된 릴리스가 없습니다.')).toBeInTheDocument()
})
