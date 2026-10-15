import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ImportExportPanel } from './ImportExportPanel.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
const props = { projectRef: 'demo.json', caseItems: ['imported/hello-1/curl.json'], refresh: vi.fn() }
const item = { index: 0, reference: props.caseItems[0], document: { request: { method: 'GET', url: 'https://example.test' } }, digest: 'preview-digest', conflict: false, blocked: false }
const preview = { items: [item], environment: null, warnings: ['인증 헤더를 제거했습니다.'] }
beforeEach(() => { api.mockReset(); props.refresh.mockReset() })
async function inspect() {
  fireEvent.change(screen.getByLabelText('가져올 원본'), { target: { value: 'curl https://example.test' } })
  fireEvent.click(screen.getByRole('button', { name: '가져오기 미리보기', exact: true }))
  await screen.findByRole('button', { name: '이 항목 저장' })
}
it('previews first, then saves the selected digest without executing requests', async () => {
  api.mockImplementation(async path => path.endsWith('/preview') ? preview : { reference: item.reference, revision: 1 })
  render(<ImportExportPanel {...props} />)
  await inspect()
  expect(api).toHaveBeenCalledTimes(1)
  expect(screen.getByText('인증 헤더를 제거했습니다.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '이 항목 저장' }))
  expect(await screen.findByRole('status')).toHaveTextContent('저장 완료')
  expect(JSON.parse(api.mock.calls[1][1].body)).toEqual({ project: 'demo.json', format: 'curl', source: 'curl https://example.test', tag: 'imported', index: 0, digest: 'preview-digest', overwrite: false })
  expect(props.refresh).toHaveBeenCalledOnce()
})
it('invalidates a preview when source or format changes', async () => {
  api.mockResolvedValue(preview)
  render(<ImportExportPanel {...props} />)
  await inspect()
  fireEvent.change(screen.getByLabelText('가져올 원본'), { target: { value: 'curl https://other.test' } })
  expect(screen.queryByRole('button', { name: '이 항목 저장' })).not.toBeInTheDocument()
  expect(api).toHaveBeenCalledTimes(1)
})
it('requires explicit overwrite for a conflict', async () => {
  api.mockResolvedValue({ ...preview, items: [{ ...item, conflict: true }] })
  render(<ImportExportPanel {...props} />)
  await inspect()
  expect(screen.getByRole('button', { name: '이 항목 저장' })).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', { name: '기존 항목 덮어쓰기 확인' }))
  expect(screen.getByRole('button', { name: '이 항목 저장' })).toBeEnabled()
})
it('clears stale previews on a server conflict and does not automatically retry', async () => {
  api.mockImplementation(async path => { if (path.endsWith('/preview')) return preview; throw new Error('미리보기를 다시 확인하세요.') })
  render(<ImportExportPanel {...props} />)
  await inspect(); fireEvent.click(screen.getByRole('button', { name: '이 항목 저장' }))
  expect(await screen.findByRole('status')).toHaveTextContent('미리보기를 다시 확인하세요.')
  expect(screen.queryByRole('button', { name: '이 항목 저장' })).not.toBeInTheDocument()
  expect(api).toHaveBeenCalledTimes(2)
})
it('exports only after selecting a case and clicking', async () => {
  api.mockResolvedValue({ curl: "curl --url 'https://example.test'", warnings: [] })
  render(<ImportExportPanel {...props} />)
  expect(api).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('내보낼 케이스'), { target: { value: item.reference } })
  fireEvent.click(screen.getByRole('button', { name: 'cURL 생성' }))
  await waitFor(() => expect(screen.getByLabelText('내보낸 cURL')).toHaveValue("curl --url 'https://example.test'"))
  expect(api.mock.calls[0][0]).toBe('/api/interoperability/curl')
})
