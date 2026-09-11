import { TestSidebar } from '../../components/ProjectSidebar.jsx'
import { api } from '../../utils/studio.js'
import { useState } from 'react'

function PipelineList({ pipelineItems, projectRef, project, refresh, onNavigate, onProjectList, onCreate, onOpen }) {
  const [notice, setNotice] = useState('')
  const removePipeline = async reference => {
    if (!window.confirm(`${reference} 파이프라인을 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    try { await api(`/api/pipelines/${encodeURIComponent(reference)}`, { method: 'DELETE' }); await refresh(); setNotice(`삭제됨: pipelines/${reference}`) } catch (error) { setNotice(error.message) }
  }
  return <div className="workspace"><TestSidebar active="pipeline" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">PIPELINES</p><h2>파이프라인 목록 <span className="count">{pipelineItems.length}</span></h2></div><button className="primary" onClick={onCreate}>＋ 새 파이프라인</button></div>{pipelineItems.length ? <div className="case-list">{pipelineItems.map(reference => <article className="case-list-item" key={reference}><button className="case-list-row" onClick={() => onOpen(reference)}><span className="case-list-icon">P</span><span><strong>{reference.replace(/\.json$/, '')}</strong><small>{reference}</small></span><span className="case-list-action">수정 · 실행 <b>→</b></span></button><button className="case-list-delete" aria-label={`${reference} 파이프라인 삭제`} title="파이프라인 삭제" onClick={() => removePipeline(reference)}>×</button></article>)}</div> : <div className="empty">저장된 파이프라인이 없습니다. 새 파이프라인을 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main></div>
}

export { PipelineList }
