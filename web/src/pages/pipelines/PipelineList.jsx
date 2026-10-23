import { TestSidebar } from '../../components/ProjectSidebar.jsx'
import { api } from '../../utils/studio.js'
import { useEffect, useState } from 'react'

function PipelineList({ projectRef, project, onNavigate, onProjectList, onCreate, onOpen, filters = {}, onFiltersChange, refreshKey = 0 }) {
  const { q = '', sort = 'reference_asc', page_size = '20', cursor = '' } = filters
  const [draft, setDraft] = useState(q)
  const [page, setPage] = useState({ items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reload, setReload] = useState(0)
  const [deleting, setDeleting] = useState(false)
  const readOnly = projectRef === 'example-api.json'
  const change = values => onFiltersChange({ q, sort, page_size, cursor: '', ...values })
  useEffect(() => { setDraft(q) }, [q])
  useEffect(() => {
    let live = true
    const controller = new AbortController()
    setPage({ items: [] }); setError(''); setLoading(Boolean(projectRef))
    if (!projectRef) return () => { live = false; controller.abort() }
    const query = new URLSearchParams({ project: projectRef, page_size, q, sort, cursor })
    api(`/api/pipelines?${query}`, { signal: controller.signal }).then(result => {
      if (!live) return
      if (!result.items.length && cursor) { change({}); return }
      setPage(result)
    }).catch(issue => { if (live) setError(issue.message) }).finally(() => { if (live) setLoading(false) })
    return () => { live = false; controller.abort() }
  }, [projectRef, q, sort, page_size, cursor, refreshKey, reload])
  const removePipeline = async reference => {
    if (!window.confirm(`${reference} 파이프라인을 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    setDeleting(true)
    try {
      await api(`/api/pipelines/${encodeURIComponent(reference)}`, { method: 'DELETE' })
      setReload(value => value + 1); setNotice(`삭제됨: pipelines/${reference}`)
    } catch (issue) { setNotice(issue.message) }
    finally { setDeleting(false) }
  }
  return <div className="workspace"><TestSidebar active="pipeline" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor">
    <section className="card">
      <div className="section-header"><div><p className="eyebrow">PIPELINES</p><h2>파이프라인 목록</h2></div>
        {readOnly ? <span className="hint">읽기 전용 예제</span> : <button className="primary" disabled={!projectRef} onClick={onCreate}>＋ 새 파이프라인</button>}
      </div>
      <form className="case-list-filters" onSubmit={event => { event.preventDefault(); change({ q: draft.trim() }) }}>
        <label className="field">파이프라인 검색<input value={draft} maxLength={100} onChange={event => setDraft(event.target.value)} placeholder="파이프라인 이름 또는 파일명" /></label>
        <button type="submit" disabled={!projectRef}>검색</button>
        <label className="field">파이프라인 정렬<select value={sort} onChange={event => change({ sort: event.target.value })}>
          <option value="reference_asc">파이프라인 파일명 오름차순</option><option value="reference_desc">파이프라인 파일명 내림차순</option><option value="created_desc">최신 생성순</option>
        </select></label>
        <label className="field">페이지 크기<select value={page_size} onChange={event => change({ page_size: event.target.value })}>
          {[10, 20, 50, 100].map(size => <option key={size} value={size}>{size}개</option>)}
        </select></label>
      </form>
      {loading ? <p role="status">파이프라인을 불러오는 중…</p> : error ? <div role="alert"><p>{error}</p><button onClick={() => setReload(value => value + 1)}>다시 시도</button><button onClick={() => change({ q: '', sort: 'reference_asc', page_size: '20' })}>조회 조건 초기화</button></div> : page.items.length ? <div className="case-list">{page.items.map(reference => {
        return <article className="case-list-item" key={reference}><button className="case-list-row" onClick={() => onOpen(reference)}><span className="case-list-icon">P</span><span><strong>{reference.replace(/\.json$/, '')}</strong><small>{reference}</small></span><span className="case-list-action">{readOnly ? '보기 · 실행' : '수정 · 실행'} <b>→</b></span></button>{!readOnly && <button className="case-list-delete" disabled={deleting} aria-label={`${reference} 파이프라인 삭제`} title="파이프라인 삭제" onClick={() => removePipeline(reference)}>×</button>}</article>
      })}</div> : <div className="empty">{!projectRef ? '프로젝트를 선택하세요.' : q ? '검색 결과가 없습니다.' : '저장된 파이프라인이 없습니다. 새 파이프라인을 만들어 시작하세요.'}</div>}
      <nav aria-label="파이프라인 페이지" className="actions case-pagination"><button disabled={loading || deleting || !!error || !page.previousCursor} onClick={() => change({ cursor: page.previousCursor })}>이전 페이지</button><span aria-live="polite">{!loading && !error ? `${page.items.length}개 표시` : ''}</span><button disabled={loading || deleting || !!error || !page.nextCursor} onClick={() => change({ cursor: page.nextCursor })}>다음 페이지</button></nav>
    </section>
    {notice && <p className="notice" role="status">{notice}</p>}
  </main></div>
}

export { PipelineList }
