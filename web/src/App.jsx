import { ApiCallPage } from './pages/api-call/ApiCallPage.jsx'
import { ProjectList } from './pages/projects/ProjectList.jsx'
import { ProjectSettings } from './pages/project-settings/ProjectSettings.jsx'
import { CaseList } from './pages/cases/CaseList.jsx'
import { CaseEditor } from './pages/case-editor/CaseEditor.jsx'
import { PipelineList } from './pages/pipelines/PipelineList.jsx'
import { PipelineEditor } from './pages/pipeline-editor/PipelineEditor.jsx'
import { ApiList } from './pages/apis/ApiList.jsx'
import { ApiAuthorEditor } from './pages/api-create/ApiAuthorEditor.jsx'
import { ClientGenerator } from './pages/generator/ClientGenerator.jsx'
import { ExecutionDashboard } from './pages/dashboard/ExecutionDashboard.jsx'
import { api } from './utils/studio.js'
import { Component, useEffect, useState } from 'react'
import { useRoute, navigateTo } from './router.js'
import packageJson from '../package.json'

function StudioApp() {
  const route = useRoute()
  const { tab, projectSettingsReference, caseReference, pipelineReference } = route
  const [projects, setProjects] = useState([])
  const [projectDetails, setProjectDetails] = useState({})
  const [activeProject, setActiveProject] = useState(route.activeProject || '')
  const [project, setProject] = useState(null)
  const [caseItems, setCaseItems] = useState([])
  const [pipelineItems, setPipelineItems] = useState([])
  const [error, setError] = useState('')
  const [dashboardRefresh, setDashboardRefresh] = useState(0)

  const refresh = async preferredProject => {
    try {
      const targetProject = preferredProject !== undefined ? preferredProject : (route.activeProject || activeProject)
      const projectData = await api('/api/projects')
      const selectedProject = projectData.items.includes(targetProject) ? targetProject : (projectData.items[0] || '')
      const filter = selectedProject ? `?project=${encodeURIComponent(selectedProject)}` : '?project=__none__'
      const [cases, pipelines, selectedDocument] = await Promise.all([
        api(`/api/cases${filter}`), api(`/api/pipelines${filter}`), selectedProject ? api(`/api/projects/${encodeURIComponent(selectedProject)}`) : Promise.resolve(null),
      ])
      setProjects(projectData.items); setProjectDetails(projectData.details || {}); setActiveProject(selectedProject); setProject(selectedDocument); setCaseItems(cases.items); setPipelineItems(pipelines.items); setError('')
      if (selectedProject && !route.activeProject && tab !== 'project' && tab !== 'project-settings' && tab !== 'api-call' && tab !== 'dashboard') {
        navigateTo({ ...route, activeProject: selectedProject }, { replace: true })
      }
    } catch (requestError) { setError(`서버 연결 오류: ${requestError.message}`) }
  }

  useEffect(() => { refresh(route.activeProject) }, [])

  useEffect(() => {
    if (route.activeProject && route.activeProject !== activeProject) {
      refresh(route.activeProject)
    }
  }, [route.activeProject])

  const selectProject = async reference => {
    navigateTo({ ...route, activeProject: reference })
    await refresh(reference)
  }
  const openProject = async reference => {
    navigateTo({ tab: 'case-list', activeProject: reference })
    await refresh(reference)
  }
  const saveProjectAndOpen = async reference => { await openProject(reference) }
  const createProject = () => { navigateTo({ tab: 'project-settings', projectSettingsReference: '', activeProject: '' }) }
  const editProject = reference => { navigateTo({ tab: 'project-settings', projectSettingsReference: reference, activeProject: reference }) }
  const navigateProjectSection = target => {
    if (target === 'dashboard') navigateTo({ tab: 'dashboard', activeProject })
    else if (target === 'cases') navigateTo({ tab: 'case-list', activeProject })
    else if (target === 'pipeline') navigateTo({ tab: 'pipeline-list', activeProject })
    else if (target === 'apis') navigateTo({ tab: 'api-list', activeProject })
    else if (target === 'generator') navigateTo({ tab: 'generator', activeProject })
    else if (target === 'api-create') navigateTo({ tab: 'api-create', activeProject })
  }
  const openCase = reference => { navigateTo({ tab: 'case-settings', activeProject, caseReference: reference }) }
  const createCase = () => { navigateTo({ tab: 'case-settings', activeProject, caseReference: '' }) }
  const openPipeline = reference => { navigateTo({ tab: 'pipeline-settings', activeProject, pipelineReference: reference }) }
  const createPipeline = () => { navigateTo({ tab: 'pipeline-settings', activeProject, pipelineReference: '' }) }

  const editorProps = {
    projects, projectRef: activeProject, project, refresh,
    caseItems, pipelineItems,
    onProjectChange: selectProject,
    onNavigate: navigateProjectSection,
    onProjectList: () => navigateTo({ tab: 'project' }),
  }
  const authorProps = {
    projects, projectRef: activeProject, project, refresh,
    caseItems, pipelineItems,
    onProjectChange: selectProject,
    onNavigate: navigateProjectSection,
    onProjectList: () => navigateTo({ tab: 'project' }),
  }
  const isApiCallTab = tab === 'api-call'
  const isDashboardTab = tab === 'dashboard'
  return <><header className="topbar"><div className="brand"><img className="brand-logo" src="/logo.png" alt="API Develop Studio" /><div><strong>API Develop Studio</strong><span className="brand-version">v{packageJson.version}</span></div></div><nav><button className={isApiCallTab ? 'selected' : ''} onClick={() => navigateTo({ tab: 'api-call', activeProject })}>API 호출</button><button className={!isApiCallTab && !isDashboardTab ? 'selected' : ''} onClick={() => navigateTo({ tab: 'project', activeProject })}>프로젝트</button><button className={isDashboardTab ? 'selected' : ''} onClick={() => navigateTo({ tab: 'dashboard', activeProject: '' })}>대시보드</button></nav><button className="ghost refresh" onClick={() => { refresh(); setDashboardRefresh(value => value + 1) }}>↻ 새로고침</button></header>{error && <div className="connection-error">{error} — Python 서버를 먼저 실행하세요: <code>python3 react_server.py</code></div>}{tab === 'dashboard' ? <ExecutionDashboard projects={projects} projectDetails={projectDetails} projectRef={route.activeProject || ''} onProjectChange={reference => navigateTo({ tab: 'dashboard', activeProject: reference })} onOpenCases={() => navigateTo({ tab: 'case-list', activeProject: route.activeProject })} refreshKey={dashboardRefresh} /> : tab === 'api-call' ? <ApiCallPage /> : tab === 'project' ? <ProjectList projects={projects} projectDetails={projectDetails} activeProject={activeProject} onOpenProject={openProject} onCreateProject={createProject} onEditProject={editProject} refresh={refresh} /> : tab === 'project-settings' ? <ProjectSettings projects={projects} projectReference={projectSettingsReference} onSaved={saveProjectAndOpen} onCancel={() => navigateTo({ tab: 'project' })} /> : tab === 'case-list' ? <CaseList {...editorProps} onCreate={createCase} onOpen={openCase} /> : tab === 'case-settings' ? <CaseEditor {...editorProps} caseReference={caseReference} onBack={() => navigateProjectSection('cases')} /> : tab === 'pipeline-list' ? <PipelineList {...editorProps} onCreate={createPipeline} onOpen={openPipeline} /> : tab === 'pipeline-settings' ? <PipelineEditor {...editorProps} pipelineReference={pipelineReference} onBack={() => navigateProjectSection('pipeline')} /> : tab === 'api-list' ? <ApiList {...authorProps} onCreate={() => navigateTo({ tab: 'api-create', activeProject })} /> : tab === 'api-create' ? <ApiAuthorEditor {...authorProps} onSaved={() => navigateTo({ tab: 'api-list', activeProject })} /> : <ClientGenerator {...authorProps} />}</>
}

class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return <main className="fatal-error"><p className="eyebrow">UNEXPECTED ERROR</p><h1>화면을 표시할 수 없습니다.</h1><p>{this.state.error.message}</p><button className="primary" onClick={() => window.location.reload()}>새로고침</button></main>
    return this.props.children
  }
}

function App() {
  return <ErrorBoundary><StudioApp /></ErrorBoundary>
}

export default App
