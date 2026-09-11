import { TestSidebar } from '../../components/ProjectSidebar.jsx'
import { caseName, api } from '../../utils/studio.js'
import { useState } from 'react'

function CaseList({ caseItems, projectRef, project, refresh, onNavigate, onProjectList, onCreate, onOpen }) {
  const [notice, setNotice] = useState('')
  const removeCase = async reference => {
    if (!window.confirm(`${reference} 케이스를 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    try { await api(`/api/cases/${encodeURIComponent(reference)}`, { method: 'DELETE' }); await refresh(); setNotice(`삭제됨: case/${reference}`) } catch (error) { setNotice(error.message) }
  }
  return <div className="workspace"><TestSidebar active="cases" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">API CASES</p><h2>API 케이스 목록 <span className="count">{caseItems.length}</span></h2></div><button className="primary" onClick={onCreate}>＋ 새 케이스</button></div>{caseItems.length ? <div className="case-list">{caseItems.map(reference => { const [tag, apiName, fileName] = reference.split('/'); return <article className="case-list-item" key={reference}><button className="case-list-row" onClick={() => onOpen(reference)}><span className="case-list-icon">{tag?.slice(0, 1).toUpperCase() || 'A'}</span><span><strong>{caseName(fileName) || reference}</strong><small>{tag} · {apiName}</small></span><span className="case-list-action">수정 · 실행 <b>→</b></span></button><button className="case-list-delete" aria-label={`${reference} 케이스 삭제`} title="케이스 삭제" onClick={() => removeCase(reference)}>×</button></article> })}</div> : <div className="empty">저장된 API 케이스가 없습니다. 새 케이스를 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main></div>
}

export { CaseList }
