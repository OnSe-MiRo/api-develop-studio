import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { CaseList } from './CaseList.jsx'
import { api } from '../../utils/studio.js'
import { navigateTo, useRoute } from '../../router.js'
vi.mock('../../utils/studio.js', async original => ({ ...await original(), api: vi.fn() }))
vi.mock('../interoperability/ImportExportPanel.jsx', () => ({ ImportExportPanel: ({ caseItems, refresh }) => <section><p>내보내기 항목: {caseItems.join(',')}</p><button onClick={refresh}>가져오기 저장 완료</button></section> }))
const page=(items,extra={})=>({items,details:{},...extra})
function RoutedCases() {
  const route=useRoute()
  return <CaseList key={route.activeProject} projectRef={route.activeProject} project={{name:'Sample'}} filters={route.caseFilters} onFiltersChange={caseFilters=>navigateTo({tab:'case-list',activeProject:route.activeProject,caseFilters})} onOpen={()=>{}} onCreate={()=>{}} />
}
beforeEach(()=>{vi.resetAllMocks();window.history.replaceState(null,'','/cases?project=sample')})
it('fetches bounded pages and binds search, exact tag, sort and size to the URL',async()=>{
  api.mockImplementation(async path=>new URL(path,'http://localhost').searchParams.get('cursor')==='next'?page(['tag/api/z.json'],{previousCursor:'prev'}):page(['tag/api/a.json'],{nextCursor:'next'}))
  render(<RoutedCases/>);await screen.findByRole('button',{name:'tag/api/a.json 케이스 삭제'})
  expect(api.mock.calls[0][0]).toContain('project=sample.json&page_size=20')
  fireEvent.click(screen.getByRole('button',{name:'다음 페이지'}));await screen.findByRole('button',{name:'tag/api/z.json 케이스 삭제'})
  expect(window.location.search).toContain('cursor=next')
  fireEvent.change(screen.getByLabelText('케이스 검색'),{target:{value:'users'}})
  fireEvent.change(screen.getByLabelText('태그'),{target:{value:'auth'}})
  fireEvent.click(screen.getByRole('button',{name:'검색',exact:true}));await screen.findByRole('button',{name:'tag/api/a.json 케이스 삭제'})
  expect(window.location.search).toContain('q=users');expect(window.location.search).toContain('tag=auth');expect(window.location.search).not.toContain('cursor=')
  fireEvent.change(screen.getByLabelText('케이스 정렬'),{target:{value:'name_desc'}})
  fireEvent.change(screen.getByLabelText('페이지 크기'),{target:{value:'50'}})
  await waitFor(()=>expect(api.mock.calls.at(-1)[0]).toContain('page_size=50'))
  expect(window.location.search).toContain('sort=name_desc')
})
it('restores query on reload and back while rejecting stale query responses',async()=>{
  window.history.replaceState(null,'','/cases?project=sample&q=old&tag=tag&cursor=saved')
  let resolveOld
  api.mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve})).mockResolvedValue(page(['new/api/back.json']))
  render(<RoutedCases/>);expect(screen.getByLabelText('케이스 검색')).toHaveValue('old')
  window.history.replaceState(null,'','/cases?project=sample&q=back&page_size=10');fireEvent(window,new PopStateEvent('popstate'))
  await screen.findByRole('button',{name:'new/api/back.json 케이스 삭제'})
  resolveOld(page(['old/api/stale.json']))
  await waitFor(()=>expect(screen.queryByRole('button',{name:'old/api/stale.json 케이스 삭제'})).not.toBeInTheDocument())
  expect(screen.getByLabelText('케이스 검색')).toHaveValue('back')
  expect(screen.getByLabelText('태그')).toHaveValue('')
})
it('loads complete export choices only when opened and refreshes the page after import',async()=>{
  api.mockImplementation(async path=>path.includes('page_size=')?page(['tag/api/a.json']):page(['tag/api/a.json','other/api/off-page.json']))
  render(<RoutedCases/>);await screen.findByRole('button',{name:'tag/api/a.json 케이스 삭제'})
  expect(api).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button',{name:'가져오기·내보내기'}))
  await screen.findByText('내보내기 항목: tag/api/a.json,other/api/off-page.json')
  fireEvent.click(screen.getByRole('button',{name:'가져오기 저장 완료'}))
  await waitFor(()=>expect(api.mock.calls.filter(([url])=>url.includes('page_size=')).length).toBe(2))
})
it('returns to the first page after its last item is deleted',async()=>{
  window.history.replaceState(null,'','/cases?project=sample&cursor=last')
  api.mockResolvedValueOnce(page(['tag/api/last.json'],{previousCursor:'prev'})).mockResolvedValueOnce({}).mockResolvedValueOnce(page([])).mockResolvedValueOnce(page(['tag/api/first.json']))
  vi.spyOn(window,'confirm').mockReturnValue(true)
  render(<RoutedCases/>);fireEvent.click(await screen.findByRole('button',{name:'tag/api/last.json 케이스 삭제'}))
  await screen.findByRole('button',{name:'tag/api/first.json 케이스 삭제'});expect(window.location.search).not.toContain('cursor=')
})
it('resets invalid filters and preserves read-only example controls',async()=>{
  window.history.replaceState(null,'','/cases?project=example-api&cursor=bad')
  api.mockRejectedValueOnce(new Error('잘못된 커서')).mockResolvedValue(page(['example/api/get.json']))
  render(<RoutedCases/>);await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button',{name:'조회 조건 초기화'}))
  await screen.findByText('get',{exact:true})
  expect(screen.queryByRole('button',{name:'가져오기·내보내기'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/케이스 삭제/})).not.toBeInTheDocument()
})
