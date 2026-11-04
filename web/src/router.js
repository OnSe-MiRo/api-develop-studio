import { useEffect, useState } from 'react'

export function stripJson(value) {
  return typeof value === 'string' ? value.replace(/\.json$/i, '') : ''
}

export function restoreJson(value) {
  if (!value || typeof value !== 'string') return ''
  return value.toLowerCase().endsWith('.json') ? value : `${value}.json`
}

export function normalizeOutcomeSearch(value) {
  return typeof value === 'string' ? value.trim().slice(0, 200) : ''
}

export function normalizeOutcomeFilter(value) {
  return ['failures', 'contract'].includes(value) ? value : 'all'
}

export function normalizeDashboardFilters(filters = {}) {
  const days = Number(filters.days)
  const page = String(filters.page ?? '1')
  return {
    days: [7, 30, 90].includes(days) ? days : 7,
    status: ['passed', 'failed', 'error', 'timeout', 'cancelled'].includes(filters.status) ? filters.status : '',
    page: /^[1-9][0-9]{0,6}$/.test(page) && Number(page) <= 1000000 ? Number(page) : 1,
    search: typeof filters.search === 'string' ? filters.search.trim().slice(0, 200) : '',
  }
}

export function parseLocation() {
  const { pathname, search } = window.location
  const query = new URLSearchParams(search)
  const rawProject = query.get('project') || ''
  const project = restoreJson(rawProject)
  const ref = query.get('ref') || ''
  const loadFilters = {
    project: query.get('project') || '',
    scenario: query.get('scenario') || '',
    status: query.get('status') || '',
    from: query.get('from') || '',
    to: query.get('to') || '',
    cursor: query.get('cursor') || '',
  }

  if (pathname === '/load-tests/compare') {
    return { tab: 'load-test-compare', activeProject: '', loadFilters, baselineId: query.get('baseline') || '', candidateId: query.get('candidate') || '' }
  }
  if (pathname === '/load-tests' || pathname === '/load-tests/results') {
    return { tab: pathname === '/load-tests' ? 'load-tests' : 'load-test-result', activeProject: '', loadFilters, runId: query.get('run') || '' }
  }

  if (pathname === '/api-call') {
    return { tab: 'api-call', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/dashboard') {
    return { tab: 'dashboard', outcomeSearch: query.get('run') ? normalizeOutcomeSearch(query.get('caseSearch')) : '', outcomeFilter: query.get('run') ? normalizeOutcomeFilter(query.get('outcomes')) : 'all', dashboardFilters: normalizeDashboardFilters(Object.fromEntries(['days', 'status', 'page', 'search'].map(name => [name, query.get(name)]))), runId: query.get('run') || '', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
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
    return { tab: 'case-list', caseFilters: { q: query.get('q') || '', tag: query.get('tag') || '', sort: query.get('sort') || 'name_asc', page_size: query.get('page_size') || '20', cursor: query.get('cursor') || '' }, activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/pipelines/new') {
    return { tab: 'pipeline-settings', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/pipelines/editor') {
    return { tab: 'pipeline-settings', activeProject: project, caseReference: '', pipelineReference: ref, projectSettingsReference: '' }
  }
  if (pathname === '/pipelines') {
    return { tab: 'pipeline-list', pipelineFilters: { q: query.get('q') || '', sort: query.get('sort') || 'reference_asc', page_size: query.get('page_size') || '20', cursor: query.get('cursor') || '' }, activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/apis/new') {
    return { tab: 'api-create', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/apis') {
    return { tab: 'api-list', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/portal') {
    return { tab: 'portal', activeProject: project, releaseId: query.get('release') || '', caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/generator') {
    return { tab: 'generator', activeProject: project, caseReference: '', pipelineReference: '', projectSettingsReference: '' }
  }
  if (pathname === '/projects') {
    return { tab: 'project', projectFilters: { q: query.get('q') || '', sort: query.get('sort') || 'reference_asc', page_size: query.get('page_size') || '20', cursor: query.get('cursor') || '' }, activeProject: project, projectSettingsReference: '', caseReference: '', pipelineReference: '' }
  }
  if (pathname === '/') {
    return { tab: 'api-call', activeProject: project, projectSettingsReference: '', caseReference: '', pipelineReference: '' }
  }
  return { tab: 'api-call', activeProject: project, projectSettingsReference: '', caseReference: '', pipelineReference: '' }
}

export function buildUrl({ tab, activeProject, projectSettingsReference, caseReference, pipelineReference, loadFilters = {}, projectFilters = {}, caseFilters = {}, pipelineFilters = {}, dashboardFilters = {}, outcomeFilter = 'all', outcomeSearch = '', runId, baselineId, candidateId, releaseId }) {
  const query = new URLSearchParams()
  const projectSlug = stripJson(activeProject)
  let pathname = '/api-call'

  switch (tab) {
    case 'api-call':
      pathname = '/api-call'
      break
    case 'dashboard': {
      pathname = '/dashboard'
      if (projectSlug) query.set('project', projectSlug)
      const filters = normalizeDashboardFilters(dashboardFilters)
      if (filters.days !== 7) query.set('days', String(filters.days))
      if (filters.status) query.set('status', filters.status)
      if (filters.page !== 1) query.set('page', String(filters.page))
      if (filters.search) query.set('search', filters.search)
      if (runId) {
        query.set('run', runId)
        const outcome = normalizeOutcomeFilter(outcomeFilter)
        if (outcome !== 'all') query.set('outcomes', outcome)
        const search = normalizeOutcomeSearch(outcomeSearch)
        if (search) query.set('caseSearch', search)
      }
      break
    }
    case 'load-tests':
    case 'load-test-result':
    case 'load-test-compare':
      pathname = tab === 'load-tests' ? '/load-tests' : tab === 'load-test-compare' ? '/load-tests/compare' : '/load-tests/results'
      if (tab === 'load-test-result' && runId) query.set('run', runId)
      if (tab === 'load-test-compare') {
        if (baselineId) query.set('baseline', baselineId)
        if (candidateId) query.set('candidate', candidateId)
      }
      if (loadFilters.project) query.set('project', loadFilters.project)
      for (const name of ['scenario', 'status', 'from', 'to', 'cursor']) {
        if (loadFilters[name]) query.set(name, loadFilters[name])
      }
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
      for (const name of ['q', 'tag', 'sort', 'page_size', 'cursor']) {
        if (caseFilters[name]) query.set(name, caseFilters[name])
      }
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
      for (const name of ['q', 'sort', 'page_size', 'cursor']) {
        if (pipelineFilters[name]) query.set(name, pipelineFilters[name])
      }
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
    case 'portal':
      pathname = '/portal'
      if (projectSlug) query.set('project', projectSlug)
      if (releaseId) query.set('release', releaseId)
      break
    case 'generator':
      pathname = '/generator'
      if (projectSlug) query.set('project', projectSlug)
      break
    case 'project':
      pathname = '/projects'
      for (const name of ['q', 'sort', 'page_size', 'cursor']) {
        if (projectFilters[name]) query.set(name, projectFilters[name])
      }
      break
    default:
      pathname = '/api-call'
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
