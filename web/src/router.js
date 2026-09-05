import { useEffect, useState } from 'react'

export function stripJson(value) {
  return typeof value === 'string' ? value.replace(/\.json$/i, '') : ''
}

export function restoreJson(value) {
  if (!value || typeof value !== 'string') return ''
  return value.toLowerCase().endsWith('.json') ? value : `${value}.json`
}

export function parseLocation() {
  const { pathname, search } = window.location
  const query = new URLSearchParams(search)
  const rawProject = query.get('project') || ''
  const project = restoreJson(rawProject)
  const ref = query.get('ref') || ''

  if (pathname === '/dashboard') {
    return { tab: 'dashboard', activeProject: project, projectSettingsReference: '', caseReference: '', pipelineReference: '' }
  }
  if (pathname === '/projects/new') {
    return { tab: 'project-settings', projectSettingsReference: '', activeProject: '', caseReference: '', pipelineReference: '' }
  }
  if (pathname === '/projects/settings') {
    return { tab: 'project-settings', projectSettingsReference: restoreJson(ref || rawProject), activeProject: project, caseReference: '', pipelineReference: '' }
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
  const projectSlug = stripJson(activeProject)
  let pathname = '/'

  switch (tab) {
    case 'dashboard':
      pathname = '/dashboard'
      if (projectSlug) query.set('project', projectSlug)
      break
    case 'project-settings':
      if (projectSettingsReference) {
        pathname = '/projects/settings'
        query.set('project', stripJson(projectSettingsReference))
      } else {
        pathname = '/projects/new'
      }
      break
    case 'case-list':
      pathname = '/cases'
      if (projectSlug) query.set('project', projectSlug)
      break
    case 'case-settings':
      if (caseReference) {
        pathname = '/cases/editor'
        if (projectSlug) query.set('project', projectSlug)
        query.set('ref', caseReference)
      } else {
        pathname = '/cases/new'
        if (projectSlug) query.set('project', projectSlug)
      }
      break
    case 'pipeline-list':
      pathname = '/pipelines'
      if (projectSlug) query.set('project', projectSlug)
      break
    case 'pipeline-settings':
      if (pipelineReference) {
        pathname = '/pipelines/editor'
        if (projectSlug) query.set('project', projectSlug)
        query.set('ref', pipelineReference)
      } else {
        pathname = '/pipelines/new'
        if (projectSlug) query.set('project', projectSlug)
      }
      break
    case 'api-list':
      pathname = '/apis'
      if (projectSlug) query.set('project', projectSlug)
      break
    case 'api-create':
      pathname = '/apis/new'
      if (projectSlug) query.set('project', projectSlug)
      break
    case 'generator':
      pathname = '/generator'
      if (projectSlug) query.set('project', projectSlug)
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
