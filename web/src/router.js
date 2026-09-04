import { useEffect, useState } from 'react'

export function parseLocation() {
  const { pathname, search } = window.location
  const query = new URLSearchParams(search)
  const project = query.get('project') || ''
  const ref = query.get('ref') || ''

  if (pathname === '/projects/new') {
    return { tab: 'project-settings', projectSettingsReference: '', activeProject: '', caseReference: '', pipelineReference: '' }
  }
  if (pathname === '/projects/settings') {
    return { tab: 'project-settings', projectSettingsReference: ref || project, activeProject: project, caseReference: '', pipelineReference: '' }
  }
  if (pathname === '/cases/new') {
    return { tab: 'case-settings', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/cases/editor') {
    return { tab: 'case-settings', activeProject: project, caseReference: ref, pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/cases') {
    return { tab: 'case-list', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/pipelines/new') {
    return { tab: 'pipeline-settings', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/pipelines/editor') {
    return { tab: 'pipeline-settings', activeProject: project, caseReference: '', pipelineReference: ref, projectSettingsReference: '' }
  }
  if (pathname === '/pipelines') {
    return { tab: 'pipeline-list', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/apis/new') {
    return { tab: 'api-create', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/apis') {
    return { tab: 'api-list', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/generator') {
    return { tab: 'generator', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  return { tab: 'project', activeProject: project, projectSettingsReference: '', caseReference: '', pipelineReference: '' }
}

export function buildUrl({ tab, activeProject, projectSettingsReference, caseReference, pipelineReference }) {
  const query = new URLSearchParams()
  let pathname = '/'

  switch (tab) {
    case 'project-settings':
      if (projectSettingsReference) {
        pathname = '/projects/settings'
        query.set('project', projectSettingsReference)
      } else {
        pathname = '/projects/new'
      }
      break
    case 'case-list':
      pathname = '/cases'
      if (activeProject) query.set('project', activeProject)
      break
    case 'case-settings':
      if (caseReference) {
        pathname = '/cases/editor'
        if (activeProject) query.set('project', activeProject)
        query.set('ref', caseReference)
      } else {
        pathname = '/cases/new'
        if (activeProject) query.set('project', activeProject)
      }
      break
    case 'pipeline-list':
      pathname = '/pipelines'
      if (activeProject) query.set('project', activeProject)
      break
    case 'pipeline-settings':
      if (pipelineReference) {
        pathname = '/pipelines/editor'
        if (activeProject) query.set('project', activeProject)
        query.set('ref', pipelineReference)
      } else {
        pathname = '/pipelines/new'
        if (activeProject) query.set('project', activeProject)
      }
      break
    case 'api-list':
      pathname = '/apis'
      if (activeProject) query.set('project', activeProject)
      break
    case 'api-create':
      pathname = '/apis/new'
      if (activeProject) query.set('project', activeProject)
      break
    case 'generator':
      pathname = '/generator'
      if (activeProject) query.set('project', activeProject)
      break
    case 'project':
    default:
      pathname = '/projects'
      break
  }

  const searchStr = query.toString()
  return searchStr ? `${pathname}?${searchStr}` : pathname
}

export function navigateTo(state, { replace = false } = {}) {
  const targetUrl = buildUrl(state)
  const currentUrl = window.location.pathname + window.location.search
  if (targetUrl !== currentUrl) {
    if (replace) {
      window.history.replaceState(null, '', targetUrl)
    } else {
      window.history.pushState(null, '', targetUrl)
    }
  }
  window.dispatchEvent(new Event('app-route-change'))
}

export function useRoute() {
  const [route, setRoute] = useState(() => parseLocation())

  useEffect(() => {
    const handleLocationChange = () => {
      setRoute(parseLocation())
    }

    window.addEventListener('popstate', handleLocationChange)
    window.addEventListener('app-route-change', handleLocationChange)

    return () => {
      window.removeEventListener('popstate', handleLocationChange)
      window.removeEventListener('app-route-change', handleLocationChange)
    }
  }, [])

  return route
}
