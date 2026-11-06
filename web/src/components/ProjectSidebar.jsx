import { ReferencePicker } from './ReferencePicker.jsx'


function ProjectSidebar({ active, projectRef, project, onProjectChange, onNavigate, onProjectList }) {
  const projectName = project?.name || (projectRef ? projectRef.replace(/\.json$/, '') : '프로젝트 미선택')
  return (
    <aside className="sidebar">
      <button className="sidebar-back" onClick={onProjectList}>← 프로젝트 목록</button>
      <div className="sidebar-title">현재 프로젝트</div>
      {onProjectChange ? (
        <ReferencePicker resource="projects" label="프로젝트 선택" value={projectRef} placeholder="프로젝트 선택" onChange={onProjectChange} />
      ) : (
        <div className="current-project">
          <strong>{projectName}</strong>
          {project?.base_url && <code>{project.base_url}</code>}
        </div>
      )}
      {project?.base_url && onProjectChange && (
        <p className="hint"><code>{project.base_url}</code></p>
      )}
      <div className="sidebar-title">테스트 구성</div>
      <div className="side-nav">
        <button className={active === 'dashboard' ? 'active' : ''} onClick={() => onNavigate('dashboard')}>
          실행 대시보드
        </button>
        <button className={active === 'cases' ? 'active' : ''} onClick={() => onNavigate('cases')}>
          API 케이스
        </button>
        <button className={active === 'pipeline' ? 'active' : ''} onClick={() => onNavigate('pipeline')}>
          파이프라인
        </button>
      </div>
      <div className="sidebar-title">API 작성</div>
      <div className="side-nav">
        <button className={active === 'apis' ? 'active' : ''} onClick={() => onNavigate('apis')}>
          API 목록 및 API 작성
        </button>
        <button className={active === 'portal' ? 'active' : ''} onClick={() => onNavigate('portal')}>개발자 문서</button>
        <button className={active === 'generator' ? 'active' : ''} onClick={() => onNavigate('generator')}>
          SDK 생성
        </button>
      </div>
    </aside>
  )
}

function TestSidebar(props) {
  return <ProjectSidebar {...props} />
}

function AuthorSidebar(props) {
  return <ProjectSidebar {...props} />
}

export { ProjectSidebar, TestSidebar, AuthorSidebar }
