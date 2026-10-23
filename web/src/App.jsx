import { AuthenticationGate, SessionControls } from './auth/AuthenticationGate.jsx'
import { WorkspaceMembers } from './auth/WorkspaceMembers.jsx'
import { ApiCallPage } from './pages/api-call/ApiCallPage.jsx'
import { ProjectList } from './pages/projects/ProjectList.jsx'
import { ProjectSettings } from './pages/project-settings/ProjectSettings.jsx'
import { CaseList } from './pages/cases/CaseList.jsx'
import { CaseEditor } from './pages/case-editor/CaseEditor.jsx'
import { PipelineList } from './pages/pipelines/PipelineList.jsx'
import { PipelineEditor } from './pages/pipeline-editor/PipelineEditor.jsx'
import { ApiList } from './pages/apis/ApiList.jsx'
import { ApiAuthorEditor } from './pages/api-create/ApiAuthorEditor.jsx'
import { DeveloperPortal } from './pages/portal/DeveloperPortal.jsx'
import { ClientGenerator } from './pages/generator/ClientGenerator.jsx'
import { ExecutionDashboard } from './pages/dashboard/ExecutionDashboard.jsx'
import { LoadTestDashboard } from './pages/load-tests/LoadTestDashboard.jsx'
import { StudioShell } from './components/StudioShell.jsx'
import { api } from './utils/studio.js'
import { Component, useEffect, useState } from 'react'
import { useRoute, navigateTo } from './router.js'

function StudioApp({ authSession, authActions }) {
  const [managing, setManaging] = useState(false)
  useEffect(() => { if (!['owner', 'admin'].includes(authSession?.workspace?.role)) setManaging(false) }, [authSession?.workspace?.role])
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

  const refresh = async (preferredProject, targetTab = tab) => {
    if (tab === 'project' && !preferredProject) return
    try {
      const targetProject = preferredProject !== undefined ? preferredProject : (route.activeProject || activeProject)
      const projectData = await api('/api/projects')
      const selectedProject = projectData.items.includes(targetProject) ? targetProject : (projectData.items[0] || '')
      const filter = selectedProject ? `?project=${encodeURIComponent(selectedProject)}` : '?project=__none__'
      const [cases, pipelines, selectedDocument] = await Promise.all([
        ['case-list', 'pipeline-list'].includes(targetTab) ? Promise.resolve({ items: [] }) : api(`/api/cases${filter}`), ['case-list', 'pipeline-list'].includes(targetTab) ? Promise.resolve({ items: [] }) : api(`/api/pipelines${filter}`), selectedProject ? api(`/api/projects/${encodeURIComponent(selectedProject)}`) : Promise.resolve(null),
      ])
      setProjects(projectData.items); setProjectDetails(projectData.details || {}); setActiveProject(selectedProject); setProject(selectedDocument); setCaseItems(cases.items); setPipelineItems(pipelines.items); setError('')
      if (selectedProject && !route.activeProject && tab !== 'project' && tab !== 'project-settings' && tab !== 'api-call' && tab !== 'dashboard' && tab !== 'load-tests' && tab !== 'load-test-result' && tab !== 'load-test-compare') {
        navigateTo({ ...route, activeProject: selectedProject }, { replace: true })
      }
    } catch (requestError) { setError(`서버 연결 오류: ${requestError.message}`) }
  }

  useEffect(() => { refresh(route.activeProject) }, [tab])

  useEffect(() => {
    if (route.activeProject && route.activeProject !== activeProject) {
      refresh(route.activeProject)
    }
  }, [route.activeProject])

  const selectProject = async reference => {
    navigateTo({ ...route, activeProject: reference, releaseId: reference === activeProject ? route.releaseId : '' })
    await refresh(reference)
  }
  const openProject = async reference => {
    navigateTo({ tab: 'case-list', activeProject: reference })
    await refresh(reference, 'case-list')
  }
  const saveProjectAndOpen = async reference => { await openProject(reference) }
  const createProject = () => { navigateTo({ tab: 'project-settings', projectSettingsReference: '', activeProject: '' }) }
  const editProject = reference => { navigateTo({ tab: 'project-settings', projectSettingsReference: reference, activeProject: reference }) }
  const navigateProjectSection = target => {
    const selectedProject = route.activeProject || activeProject
    if (target === 'dashboard') navigateTo({ tab: 'dashboard', activeProject: selectedProject })
    else if (target === 'cases') navigateTo({ tab: 'case-list', activeProject: selectedProject })
    else if (target === 'pipeline') navigateTo({ tab: 'pipeline-list', activeProject: selectedProject })
    else if (target === 'apis') navigateTo({ tab: 'api-list', activeProject: selectedProject })
    else if (target === 'portal') navigateTo({ tab: 'portal', activeProject: selectedProject })
    else if (target === 'generator') navigateTo({ tab: 'generator', activeProject: selectedProject })
    else if (target === 'api-create') navigateTo({ tab: 'api-create', activeProject: selectedProject })
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
  return <StudioShell sessionControls={<SessionControls info={authSession} actions={authActions} onManage={() => setManaging(value => !value)} />} tab={tab} activeProject={activeProject} error={error} onNavigate={navigateTo} onRefresh={() => { refresh(); setDashboardRefresh(value => value + 1) }}>
    {managing && <WorkspaceMembers onClose={() => setManaging(false)} />}
    {!managing && (tab === 'load-tests' || tab === 'load-test-result' || tab === 'load-test-compare' ? <LoadTestDashboard route={route} projects={projects} projectDetails={projectDetails} refreshKey={dashboardRefresh} /> : tab === 'dashboard' ? <ExecutionDashboard projects={projects} projectDetails={projectDetails} projectRef={route.activeProject || ''} onProjectChange={reference => navigateTo({ tab: 'dashboard', activeProject: reference })} onOpenCases={() => navigateTo({ tab: 'case-list', activeProject: route.activeProject })} refreshKey={dashboardRefresh} /> : tab === 'api-call' ? <ApiCallPage /> : tab === 'project' ? <ProjectList filters={route.projectFilters} onFiltersChange={projectFilters => navigateTo({ tab: 'project', projectFilters })} refreshKey={dashboardRefresh} activeProject={activeProject} onOpenProject={openProject} onCreateProject={createProject} onEditProject={editProject} /> : tab === 'project-settings' ? <ProjectSettings projects={projects} projectReference={projectSettingsReference} onSaved={saveProjectAndOpen} onCancel={() => navigateTo({ tab: 'project' })} /> : tab === 'case-list' ? <CaseList {...editorProps} key={activeProject} filters={route.caseFilters} onFiltersChange={caseFilters => navigateTo({ tab: 'case-list', activeProject, caseFilters })} refreshKey={dashboardRefresh} onCreate={createCase} onOpen={openCase} /> : tab === 'case-settings' ? <CaseEditor {...editorProps} caseReference={caseReference} onBack={() => navigateProjectSection('cases')} /> : tab === 'pipeline-list' ? <PipelineList {...editorProps} key={activeProject} filters={route.pipelineFilters} onFiltersChange={pipelineFilters => navigateTo({ tab: 'pipeline-list', activeProject, pipelineFilters })} refreshKey={dashboardRefresh} onCreate={createPipeline} onOpen={openPipeline} /> : tab === 'pipeline-settings' ? <PipelineEditor {...editorProps} pipelineReference={pipelineReference} onBack={() => navigateProjectSection('pipeline')} /> : tab === 'api-list' ? <ApiList {...authorProps} onCreate={() => navigateTo({ tab: 'api-create', activeProject })} /> : tab === 'api-create' ? <ApiAuthorEditor {...authorProps} onSaved={() => navigateTo({ tab: 'api-list', activeProject })} /> : tab === 'portal' ? <DeveloperPortal {...authorProps} releaseId={route.releaseId} onSelectRelease={releaseId => navigateTo({ tab: 'portal', activeProject, releaseId })} /> : <ClientGenerator {...authorProps} />)}
  </StudioShell>
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
  return <ErrorBoundary><AuthenticationGate>{(session, actions) => <StudioApp key={`${session.userId}:${session.workspace.id}`} authSession={session} authActions={actions} />}</AuthenticationGate></ErrorBoundary>
}

export default App
