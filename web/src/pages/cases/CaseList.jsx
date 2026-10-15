import { TestSidebar } from '../../components/ProjectSidebar.jsx'
import { caseName, api } from '../../utils/studio.js'
import { useEffect, useState } from 'react'
import { ImportExportPanel } from '../interoperability/ImportExportPanel.jsx'

function CaseList({ projectRef, project, onNavigate, onProjectList, onCreate, onOpen, filters = {}, onFiltersChange, refreshKey = 0 }) {
  const { q = '', tag = '', sort = 'name_asc', page_size = '20', cursor = '' } = filters
  const [draft, setDraft] = useState(q)
  const [draftTag, setDraftTag] = useState(tag)
  const [page, setPage] = useState({ items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reload, setReload] = useState(0)
  const [deleting, setDeleting] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [exportItems, setExportItems] = useState([])
  const [exportLoading, setExportLoading] = useState(false)
  const [exportError, setExportError] = useState('')
  const readOnly = projectRef === 'example-api.json'
  const change = values => onFiltersChange({ q, tag, sort, page_size, cursor: '', ...values })
  useEffect(() => { setDraft(q); setDraftTag(tag) }, [q, tag])
  useEffect(() => {
    let live = true
    const controller = new AbortController()
    setPage({ items: [] }); setError(''); setLoading(Boolean(projectRef))
    if (!projectRef) return () => { live = false; controller.abort() }
    const query = new URLSearchParams({ project: projectRef, page_size, q, tag, sort, cursor })
    api(`/api/cases?${query}`, { signal: controller.signal }).then(result => {
      if (!live) return
      if (!result.items.length && cursor) { change({}); return }
      setPage(result)
    }).catch(issue => { if (live) setError(issue.message) }).finally(() => { if (live) setLoading(false) })
    return () => { live = false; controller.abort() }
  }, [projectRef, q, tag, sort, page_size, cursor, refreshKey, reload])
  // Export selection must still include all cases, not just the displayed page.
  // Load it only when the user opens the import/export panel.
  useEffect(() => {
    let live = true
    const controller = new AbortController()
    setExportItems([]); setExportError(''); setExportLoading(Boolean(showImport && projectRef && !readOnly))
    if (showImport && projectRef && !readOnly) {
      api(`/api/cases?project=${encodeURIComponent(projectRef)}`, { signal: controller.signal }).then(result => {
        if (live) setExportItems(result.items)
      }).catch(issue => { if (live) setExportError(issue.message) }).finally(() => { if (live) setExportLoading(false) })
    }
    return () => { live = false; controller.abort() }
  }, [showImport, projectRef, readOnly, reload, refreshKey])
  const removeCase = async reference => {
    if (!window.confirm(`${reference} 케이스를 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    setDeleting(true)
    try {
      await api(`/api/cases/${encodeURIComponent(reference)}`, { method: 'DELETE' })
      setReload(value => value + 1); setNotice(`삭제됨: case/${reference}`)
    } catch (issue) { setNotice(issue.message) }
    finally { setDeleting(false) }
  }
  const afterImport = async () => { change({}); setReload(value => value + 1) }
  return <div className="workspace"><TestSidebar active="cases" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor">
    <section className="card">
      <div className="section-header"><div><p className="eyebrow">API CASES</p><h2>API 케이스 목록</h2></div>
        {readOnly ? <span className="hint">읽기 전용 예제</span> : <div className="generator-actions"><button className="ghost" disabled={!projectRef} onClick={() => setShowImport(value => !value)}>가져오기·내보내기</button><button className="primary" disabled={!projectRef} onClick={onCreate}>＋ 새 케이스</button></div>}
      </div>
      <form className="case-list-filters" onSubmit={event => { event.preventDefault(); change({ q: draft.trim(), tag: draftTag.trim() }) }}>
        <label className="field">케이스 검색<input value={draft} maxLength={100} onChange={event => setDraft(event.target.value)} placeholder="케이스 이름 또는 API 이름" /></label>
        <label className="field">태그<input value={draftTag} maxLength={128} onChange={event => setDraftTag(event.target.value)} placeholder="전체 태그 · 입력 시 정확히 일치" /></label>
        <button type="submit" disabled={!projectRef}>검색</button>
        <label className="field">케이스 정렬<select value={sort} onChange={event => change({ sort: event.target.value })}>
          <option value="name_asc">케이스 파일명 오름차순</option><option value="name_desc">케이스 파일명 내림차순</option><option value="created_desc">최신 생성순</option>
        </select></label>
        <label className="field">페이지 크기<select value={page_size} onChange={event => change({ page_size: event.target.value })}>
          {[10, 20, 50, 100].map(size => <option key={size} value={size}>{size}개</option>)}
        </select></label>
      </form>
      {loading ? <p role="status">케이스를 불러오는 중…</p> : error ? <div role="alert"><p>{error}</p><button onClick={() => setReload(value => value + 1)}>다시 시도</button><button onClick={() => change({ q: '', tag: '', sort: 'name_asc', page_size: '20' })}>조회 조건 초기화</button></div> : page.items.length ? <div className="case-list">{page.items.map(reference => {
        const [caseTag, apiName, fileName] = reference.split('/')
        return <article className="case-list-item" key={reference}><button className="case-list-row" onClick={() => onOpen(reference)}><span className="case-list-icon">{caseTag?.slice(0, 1).toUpperCase() || 'A'}</span><span><strong>{caseName(fileName) || reference}</strong><small>{caseTag} · {apiName}</small></span><span className="case-list-action">{readOnly ? '보기 · 실행' : '수정 · 실행'} <b>→</b></span></button>{!readOnly && <button className="case-list-delete" disabled={deleting} aria-label={`${reference} 케이스 삭제`} title="케이스 삭제" onClick={() => removeCase(reference)}>×</button>}</article>
      })}</div> : <div className="empty">{!projectRef ? '프로젝트를 선택하세요.' : q || tag ? '검색 결과가 없습니다.' : '저장된 API 케이스가 없습니다. 새 케이스를 만들어 시작하세요.'}</div>}
      <nav aria-label="케이스 페이지" className="actions case-pagination"><button disabled={loading || deleting || !!error || !page.previousCursor} onClick={() => change({ cursor: page.previousCursor })}>이전 페이지</button><span aria-live="polite">{!loading && !error ? `${page.items.length}개 표시` : ''}</span><button disabled={loading || deleting || !!error || !page.nextCursor} onClick={() => change({ cursor: page.nextCursor })}>다음 페이지</button></nav>
    </section>
    {showImport && !readOnly && <>{exportLoading && <p role="status">내보내기 케이스 목록을 불러오는 중…</p>}{exportError && <p role="alert">{exportError}<button onClick={() => setReload(value => value + 1)}>내보내기 목록 다시 시도</button></p>}<ImportExportPanel key={projectRef} projectRef={projectRef} caseItems={exportItems} refresh={afterImport} /></>}
    {notice && <p className="notice" role="status">{notice}</p>}
  </main></div>
}

export { CaseList }
