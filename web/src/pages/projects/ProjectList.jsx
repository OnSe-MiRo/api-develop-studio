import { api } from '../../utils/studio.js'
import { useState } from 'react'

function ProjectList({ projects, projectDetails, activeProject, onOpenProject, onCreateProject, onEditProject, refresh }) {
  const [notice, setNotice] = useState('')
  const removeProject = async reference => {
    if (!window.confirm(`${reference.replace(/\.json$/, '')} 프로젝트를 삭제할까요?\n연결된 파이프라인은 함께 목록에서 제거되며 변경 이력은 보관됩니다. 연결된 API 케이스가 있으면 먼저 케이스를 삭제해야 합니다.`)) return
    try {
      const result = await api(`/api/projects/${encodeURIComponent(reference)}`, { method: 'DELETE' })
      await refresh('')
      const pipelineNotice = result.deleted_pipelines?.length ? ` · 파이프라인 ${result.deleted_pipelines.length}개 함께 삭제` : ''
      setNotice(`삭제됨: projects/${reference}${pipelineNotice}`)
    } catch (error) { setNotice(error.message) }
  }
  return <main className="project-page"><section className="card project-list-card"><div className="section-header"><div><p className="eyebrow">SELECT PROJECT</p><h2>프로젝트 목록</h2></div><button className="primary" onClick={onCreateProject}>＋ 새 프로젝트 만들기</button></div>{projects.length ? <div className="project-grid">{projects.map(reference => <article className={`project-card ${activeProject === reference ? 'active' : ''}`} key={reference}><button className="project-card-open" onClick={() => onOpenProject(reference)}><span className="project-card-label">PROJECT</span><strong>{reference.replace(/\.json$/, '')}</strong><small>{projectDetails[reference]?.base_url || ''}</small><span className="project-card-action">API 테스트 열기 <b>→</b></span></button><div className="project-card-actions"><button className="project-card-edit" aria-label={`${reference} 프로젝트 수정`} title="프로젝트 수정" onClick={() => onEditProject(reference)}>수정</button><button className="project-card-delete" aria-label={`${reference} 프로젝트 삭제`} title="프로젝트 삭제" onClick={() => removeProject(reference)}>×</button></div></article>)}</div> : <div className="empty">등록된 프로젝트가 없습니다. 새 프로젝트를 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main>
}

export { ProjectList }
