import { api } from '../../utils/studio.js'
import { useEffect, useState } from 'react'

function ProjectList({ filters = {}, onFiltersChange, refreshKey = 0, activeProject, onOpenProject, onCreateProject, onEditProject }) {
  const { q = '', sort = 'reference_asc', page_size = '20', cursor = '' } = filters
  const [notice, setNotice] = useState('')
  const [draft, setDraft] = useState(q)
  const [page, setPage] = useState({ items: [], details: {} })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [deleting, setDeleting] = useState(false)
  useEffect(() => { setDraft(q) }, [q])
  useEffect(() => {
    let live = true
    const controller = new AbortController()
    setLoading(true); setError(''); setPage({ items: [], details: {} })
    const query = new URLSearchParams({ page_size, q, sort, cursor })
    api(`/api/projects?${query}`, { signal: controller.signal }).then(result => {
      if (!live) return
      if (!result.items.length && cursor) { onFiltersChange({ q, sort, page_size, cursor: '' }); return }
      setPage(result)
    }).catch(issue => { if (live) setError(issue.message) }).finally(() => { if (live) setLoading(false) })
    return () => { live = false; controller.abort() }
  }, [q, sort, page_size, cursor, refreshKey, reload])
  const projects = page.items
  const projectDetails = page.details || {}
  const change = values => onFiltersChange({ q, sort, page_size, cursor: '', ...values })
  const removeProject = async reference => {
    if (!window.confirm(`${reference.replace(/\.json$/, '')} 프로젝트를 삭제할까요?\n연결된 파이프라인은 함께 목록에서 제거되며 변경 이력은 보관됩니다. 연결된 API 케이스가 있으면 먼저 케이스를 삭제해야 합니다.`)) return
    setDeleting(true)
    try {
      const result = await api(`/api/projects/${encodeURIComponent(reference)}`, { method: 'DELETE' })
      setReload(value => value + 1)
      const pipelineNotice = result.deleted_pipelines?.length ? ` · 파이프라인 ${result.deleted_pipelines.length}개 함께 삭제` : ''
      setNotice(`삭제됨: projects/${reference}${pipelineNotice}`)
    } catch (error) { setNotice(error.message) }
    finally { setDeleting(false) }
  }
  return <main className="project-page"><section className="card project-list-card"><div className="section-header"><div><p className="eyebrow">SELECT PROJECT</p><h2>프로젝트 목록</h2></div><button className="primary" onClick={onCreateProject}>＋ 새 프로젝트 만들기</button></div>
    <form className="project-list-filters" onSubmit={event => { event.preventDefault(); change({ q: draft.trim() }) }}>
      <label className="field">프로젝트 검색<input value={draft} maxLength={100} onChange={event => setDraft(event.target.value)} placeholder="프로젝트 이름 또는 파일명" /></label>
      <button type="submit">검색</button>
      <label className="field">프로젝트 정렬<select value={sort} onChange={event => change({ sort: event.target.value })}>
        <option value="reference_asc">파일명 오름차순</option><option value="reference_desc">파일명 내림차순</option><option value="created_desc">최신 생성순</option>
      </select></label>
      <label className="field">페이지 크기<select value={page_size} onChange={event => change({ page_size: event.target.value })}>
        {[10, 20, 50, 100].map(size => <option key={size} value={size}>{size}개</option>)}
      </select></label>
    </form>
    {loading ? <p role="status">프로젝트를 불러오는 중…</p> : error ? <div role="alert"><p>{error}</p><button onClick={() => setReload(value => value + 1)}>다시 시도</button><button onClick={() => change({})}>첫 페이지</button></div> : projects.length ? <div className="project-grid">{projects.map(reference => { const isExample = reference === 'example-api.json'; return <article className={`project-card ${activeProject === reference ? 'active' : ''}`} key={reference}><button className="project-card-open" onClick={() => onOpenProject(reference)}><span className="project-card-label">{isExample ? 'READ ONLY EXAMPLE' : 'PROJECT'}</span><strong>{reference.replace(/\.json$/, '')}</strong><small>{projectDetails[reference]?.base_url || ''}</small><span className="project-card-action">API 테스트 열기 <b>→</b></span></button><div className="project-card-actions"><button className="project-card-edit" aria-label={`${reference} 프로젝트 ${isExample ? '보기' : '수정'}`} title={isExample ? '예제 값 보기' : '프로젝트 수정'} onClick={() => onEditProject(reference)}>{isExample ? '보기' : '수정'}</button>{!isExample && <button className="project-card-delete" aria-label={`${reference} 프로젝트 삭제`} title="프로젝트 삭제" disabled={deleting} onClick={() => removeProject(reference)}>×</button>}</div></article> })}</div> : <div className="empty">{q ? '검색 결과가 없습니다.' : '등록된 프로젝트가 없습니다. 새 프로젝트를 만들어 시작하세요.'}</div>}
    <nav aria-label="프로젝트 페이지" className="actions project-pagination">
      <button disabled={loading || deleting || !!error || !page.previousCursor} onClick={() => change({ cursor: page.previousCursor })}>이전 페이지</button>
      <span aria-live="polite">{!loading && !error ? `${projects.length}개 표시` : ''}</span>
      <button disabled={loading || deleting || !!error || !page.nextCursor} onClick={() => change({ cursor: page.nextCursor })}>다음 페이지</button>
    </nav></section>{notice && <p className="notice">{notice}</p>}</main>
}

export { ProjectList }
