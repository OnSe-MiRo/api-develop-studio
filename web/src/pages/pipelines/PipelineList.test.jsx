import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { PipelineList } from './PipelineList.jsx'
import { api } from '../../utils/studio.js'
import { navigateTo, useRoute } from '../../router.js'
vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
const page = (items, extra = {}) => ({ items, details: Object.fromEntries(items.map(ref => [ref, { base_url: 'https://example.test' }])), ...extra })
function RoutedList() {
  const route = useRoute()
  return <PipelineList projectRef="sample.json" project={{name:"Sample"}} filters={route.pipelineFilters} onFiltersChange={pipelineFilters => navigateTo({ tab: 'pipeline-list', activeProject: 'sample.json', pipelineFilters })} onCreate={() => {}} onOpen={() => {}} onNavigate={() => {}} />
}
beforeEach(() => { vi.resetAllMocks(); window.history.replaceState(null, '', '/pipelines?project=sample') })
it('loads bounded pages and retains search, sorting and size in the URL', async () => {
  api.mockImplementation(async path => new URL(path, 'http://localhost').searchParams.get('cursor') === 'next' ? page(['z.json'], { previousCursor: 'previous' }) : page(['a.json'], { nextCursor: 'next' }))
  render(<RoutedList />)
  await screen.findByRole('button', { name: 'a.json 파이프라인 삭제' })
  expect(api.mock.calls[0][0]).toContain('page_size=20')
  fireEvent.click(screen.getByRole('button', { name: '다음 페이지' }))
  await screen.findByRole('button', { name: 'z.json 파이프라인 삭제' })
  expect(window.location.search).toContain('cursor=next')
  expect(screen.getByRole('button', { name: '이전 페이지' })).toBeEnabled()
  fireEvent.change(screen.getByLabelText('파이프라인 검색'), { target: { value: '한글' } })
  fireEvent.click(screen.getByRole('button', { name: '검색', exact: true }))
  await screen.findByRole('button', { name: 'a.json 파이프라인 삭제' })
  expect(new URLSearchParams(window.location.search).get('q')).toBe('한글')
  expect(new URLSearchParams(window.location.search).get('cursor')).toBeNull()
  fireEvent.change(screen.getByLabelText('파이프라인 정렬'), { target: { value: 'created_desc' } })
  fireEvent.change(screen.getByLabelText('페이지 크기'), { target: { value: '50' } })
  await waitFor(() => expect(api.mock.calls.at(-1)[0]).toContain('page_size=50'))
  expect(window.location.search).toContain('sort=created_desc')
})
it('restores URL filters on mount and popstate', async () => {
  window.history.replaceState(null, '', '/pipelines?project=sample&q=old&sort=reference_desc&page_size=10&cursor=saved')
  api.mockResolvedValue(page(['restored.json']))
  render(<RoutedList />)
  await screen.findByRole('button', { name: 'restored.json 파이프라인 삭제' })
  expect(screen.getByLabelText('파이프라인 검색')).toHaveValue('old')
  expect(api.mock.calls[0][0]).toContain('cursor=saved')
  window.history.replaceState(null, '', '/pipelines?project=sample&q=back&page_size=50')
  fireEvent(window, new PopStateEvent('popstate'))
  await waitFor(() => expect(screen.getByLabelText('파이프라인 검색')).toHaveValue('back'))
  expect(api.mock.calls.at(-1)[0]).toContain('page_size=50')
})
it('ignores an older query response and offers retry on errors', async () => {
  let resolveOld
  api.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve })).mockRejectedValueOnce(new Error('커서 오류'))
  render(<RoutedList />)
  fireEvent.change(screen.getByLabelText('파이프라인 정렬'), { target: { value: 'reference_desc' } })
  await screen.findByRole('alert')
  resolveOld(page(['stale.json']))
  expect(screen.queryByRole('button', { name: 'stale.json 파이프라인 삭제' })).not.toBeInTheDocument()
  api.mockResolvedValue(page([]))
  fireEvent.click(screen.getByRole('button', { name: '다시 시도' }))
  await screen.findByText('저장된 파이프라인이 없습니다. 새 파이프라인을 만들어 시작하세요.')
})
it('returns to the first page after deleting the last item on a cursor page', async () => {
  window.history.replaceState(null, '', '/pipelines?project=sample&cursor=last')
  api.mockResolvedValueOnce(page(['last.json'], { previousCursor: 'previous' }))
    .mockResolvedValueOnce({ deleted_pipelines: [] }).mockResolvedValueOnce(page([])).mockResolvedValueOnce(page(['first.json']))
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  render(<RoutedList />)
  fireEvent.click(await screen.findByRole('button', { name: 'last.json 파이프라인 삭제' }))
  await screen.findByRole('button', { name: 'first.json 파이프라인 삭제' })
  expect(new URLSearchParams(window.location.search).get('cursor')).toBeNull()
})
