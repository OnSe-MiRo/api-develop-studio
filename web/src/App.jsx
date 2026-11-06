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
import { Component, useEffect, useRef, useState } from 'react'
import { useRoute, navigateTo } from './router.js'

function StudioApp({ authSession, authActions }) {
  const [managing, setManaging] = useState(false)
  useEffect(() => { if (!['owner', 'admin'].includes(authSession?.workspace?.role)) setManaging(false) }, [authSession?.workspace?.role])
  const route = useRoute()
  const { tab, projectSettingsReference, caseReference, pipelineReference } = route
  const [projects, setProjects] = useState([])
  const [activeProject, setActiveProject] = useState(route.activeProject || '')
  const [project, setProject] = useState(null)
  const refreshSequence = useRef(0)
  const [error, setError] = useState('')
  const [dashboardRefresh, setDashboardRefresh] = useState(0)

  const refresh = async (preferredProject, targetTab = tab) => {
    if (preferredProject === undefined) preferredProject = route.activeProject || activeProject
    const sequence = ++refreshSequence.current
    if (['project', 'api-call', 'dashboard', 'load-tests', 'load-test-result', 'load-test-compare'].includes(targetTab)) return
    try {
      if (targetTab === 'project-settings') {
        if (!projectSettingsReference) {
          // New filenames must be unique even when an existing project is on another page.
          const result = await api('/api/projects')
          if (sequence === refreshSequence.current) setProjects(result.items)
        }
        return
      }
      let selectedProject = preferredProject || ''
      const firstProject = async () => (await api('/api/projects?page_size=1')).items[0] || ''
      if (!selectedProject) selectedProject = await firstProject()
      let selectedDocument = null
      if (selectedProject) {
        try { selectedDocument = await api(`/api/projects/${encodeURIComponent(selectedProject)}`) }
        catch (failure) {
          if (!preferredProject || ![400, 404].includes(failure.status)) throw failure
          selectedProject = await firstProject()
          if (selectedProject) selectedDocument = await api(`/api/projects/${encodeURIComponent(selectedProject)}`)
        }
      }
      if (sequence !== refreshSequence.current) return
      setActiveProject(selectedProject); setProject(selectedDocument); setError('')
      if (selectedProject && selectedProject !== route.activeProject) navigateTo({ ...route, activeProject: selectedProject }, { replace: true })
    } catch (failure) {
      if (sequence === refreshSequence.current) setError(`서버 연결 오류: ${failure.message}`)
    }
  }

  useEffect(() => {
    refresh(route.activeProject)
    return () => { refreshSequence.current++ }
  }, [tab, route.activeProject, projectSettingsReference])

  const selectProject = reference => navigateTo({ ...route, activeProject: reference, releaseId: reference === activeProject ? route.releaseId : '' })
  const openProject = reference => navigateTo({ tab: 'case-list', activeProject: reference })
  const saveProjectAndOpen = reference => openProject(reference)
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
    projectRef: activeProject, project, refresh,
    onProjectChange: selectProject,
    onNavigate: navigateProjectSection,
    onProjectList: () => navigateTo({ tab: 'project' }),
  }
  const authorProps = {
    projectRef: activeProject, project, refresh,
    onProjectChange: selectProject,
    onNavigate: navigateProjectSection,
    onProjectList: () => navigateTo({ tab: 'project' }),
  }
  return <StudioShell sessionControls={<SessionControls info={authSession} actions={authActions} onManage={() => setManaging(value => !value)} />} tab={tab} activeProject={activeProject} error={error} onNavigate={navigateTo} onRefresh={() => { refresh(); setDashboardRefresh(value => value + 1) }}>
    {managing && <WorkspaceMembers onClose={() => setManaging(false)} />}
    {!managing && (tab === 'load-tests' || tab === 'load-test-result' || tab === 'load-test-compare' ? <LoadTestDashboard route={route} refreshKey={dashboardRefresh} /> : tab === 'dashboard' ? <ExecutionDashboard route={route} onNavigate={navigateTo} projectRef={route.activeProject || ''} onOpenCases={() => navigateTo({ tab: 'case-list', activeProject: route.activeProject })} refreshKey={dashboardRefresh} /> : tab === 'api-call' ? <ApiCallPage /> : tab === 'project' ? <ProjectList filters={route.projectFilters} onFiltersChange={projectFilters => navigateTo({ tab: 'project', projectFilters })} refreshKey={dashboardRefresh} activeProject={activeProject} onOpenProject={openProject} onCreateProject={createProject} onEditProject={editProject} /> : tab === 'project-settings' ? <ProjectSettings projects={projects} projectReference={projectSettingsReference} onSaved={saveProjectAndOpen} onCancel={() => navigateTo({ tab: 'project' })} /> : tab === 'case-list' ? <CaseList {...editorProps} key={activeProject} filters={route.caseFilters} onFiltersChange={caseFilters => navigateTo({ tab: 'case-list', activeProject, caseFilters })} refreshKey={dashboardRefresh} onCreate={createCase} onOpen={openCase} /> : tab === 'case-settings' ? <CaseEditor {...editorProps} caseReference={caseReference} onBack={() => navigateProjectSection('cases')} /> : tab === 'pipeline-list' ? <PipelineList {...editorProps} key={activeProject} filters={route.pipelineFilters} onFiltersChange={pipelineFilters => navigateTo({ tab: 'pipeline-list', activeProject, pipelineFilters })} refreshKey={dashboardRefresh} onCreate={createPipeline} onOpen={openPipeline} /> : tab === 'pipeline-settings' ? <PipelineEditor {...editorProps} pipelineReference={pipelineReference} onBack={() => navigateProjectSection('pipeline')} /> : tab === 'api-list' ? <ApiList {...authorProps} onCreate={() => navigateTo({ tab: 'api-create', activeProject })} /> : tab === 'api-create' ? <ApiAuthorEditor {...authorProps} onSaved={() => navigateTo({ tab: 'api-list', activeProject })} /> : tab === 'portal' ? <DeveloperPortal {...authorProps} releaseId={route.releaseId} onSelectRelease={releaseId => navigateTo({ tab: 'portal', activeProject, releaseId })} /> : <ClientGenerator {...authorProps} />)}
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
