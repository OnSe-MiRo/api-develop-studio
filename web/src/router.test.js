import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildUrl, navigateTo, parseLocation, restoreJson, stripJson } from './router.js'

describe('router', () => {
  beforeEach(() => window.history.replaceState(null, '', '/'))

  it('preserves comparison selections and list filters across URL parsing', () => {
    const url = buildUrl({ tab: 'load-test-compare', baselineId: 'base +1', candidateId: 'candidate/2', loadFilters: { project: 'demo.json', cursor: 'next+page' } })
    window.history.replaceState(null, '', url)
    expect(window.location.pathname).toBe('/load-tests/compare')
    expect(parseLocation()).toMatchObject({ tab: 'load-test-compare', baselineId: 'base +1', candidateId: 'candidate/2', loadFilters: { project: 'demo.json', cursor: 'next+page' } })
  })

  it('round-trips editor references and project slugs', () => {
    const url = buildUrl({ tab: 'case-settings', activeProject: 'sample.json', caseReference: 'users/get.json' })
    expect(url).toBe('/cases/editor?project=sample&ref=users%2Fget.json')
    window.history.replaceState(null, '', url)
    expect(parseLocation()).toMatchObject({ tab: 'case-settings', activeProject: 'sample.json', caseReference: 'users/get.json' })
  })

  it('normalizes json references and unknown paths', () => {
    expect(stripJson('sample.JSON')).toBe('sample')
    expect(restoreJson('sample')).toBe('sample.json')
    window.history.replaceState(null, '', '/unknown')
    expect(parseLocation().tab).toBe('api-call')
  })

  it('uses replaceState when requested and publishes a route event', () => {
    const replace = vi.spyOn(window.history, 'replaceState')
    const listener = vi.fn()
    window.addEventListener('app-route-change', listener, { once: true })
    navigateTo({ tab: 'dashboard', activeProject: 'sample.json' }, { replace: true })
    expect(replace).toHaveBeenCalled()
    expect(listener).toHaveBeenCalledOnce()
  })

  it('keeps load-test project references and result filters in the URL', () => {
    const filters = { project: 'demo', scenario: 'target mixed', status: 'failed', from: '2026-09-01', to: '2026-09-27', cursor: 'opaque/next' }
    const url = buildUrl({ tab: 'load-test-result', runId: 'run one', loadFilters: filters })
    window.history.replaceState(null, '', url)
    expect(parseLocation()).toMatchObject({ tab: 'load-test-result', runId: 'run one', loadFilters: filters })
    expect(buildUrl({ tab: 'load-tests', loadFilters: filters })).toContain('project=demo')
  })
})

it('preserves the selected immutable release in the portal URL', () => {
  const url = buildUrl({ tab: 'portal', activeProject: 'team/demo.json', releaseId: 'release-123' })
  expect(url).toBe('/portal?project=team%2Fdemo&release=release-123')
  window.history.replaceState(null, '', url)
  expect(parseLocation()).toMatchObject({ tab: 'portal', activeProject: 'team/demo.json', releaseId: 'release-123' })
})

it('round-trips project list query and cursor without contaminating other routes', () => {
  const projectFilters = { q: '한글 + %', sort: 'created_desc', page_size: '50', cursor: 'opaque/+=token' }
  window.history.replaceState(null, '', buildUrl({ tab: 'project', projectFilters }))
  expect(parseLocation()).toMatchObject({ tab: 'project', projectFilters })
  expect(buildUrl({ tab: 'case-list', activeProject: 'a.json', projectFilters })).toBe('/cases?project=a')
})

it('round-trips case filters and resets them on editor navigation', () => {
  const caseFilters={q:'한글 +',tag:'auth',sort:'name_desc',page_size:'50',cursor:'cursor/+=x'}
  window.history.replaceState(null,'',buildUrl({tab:'case-list',activeProject:'demo.json',caseFilters}))
  expect(parseLocation()).toMatchObject({tab:'case-list',activeProject:'demo.json',caseFilters})
  expect(buildUrl({tab:'case-settings',activeProject:'demo.json',caseReference:'tag/api/case.json',caseFilters})).not.toContain('cursor=')
})

it('round-trips pipeline page filters independently of editor routes', () => {
  const pipelineFilters={q:'한글 +',sort:'created_desc',page_size:'50',cursor:'opaque/+='}
  window.history.replaceState(null,'',buildUrl({tab:'pipeline-list',activeProject:'demo.json',pipelineFilters}))
  expect(parseLocation()).toMatchObject({tab:'pipeline-list',activeProject:'demo.json',pipelineFilters})
  expect(buildUrl({tab:'pipeline-settings',activeProject:'demo.json',pipelineReference:'a.json',pipelineFilters})).not.toContain('cursor=')
})

it('round-trips dashboard filters and selected detail with encoded values', () => {
  const dashboardFilters={days:30,status:'failed',page:2,search:'한글 + 100%'}
  const url=buildUrl({tab:'dashboard',activeProject:'team/demo.json',dashboardFilters,runId:'run +/one'})
  window.history.replaceState(null,'',url)
  expect(parseLocation()).toMatchObject({tab:'dashboard',activeProject:'team/demo.json',dashboardFilters,runId:'run +/one'})
  expect(buildUrl({tab:'case-list',activeProject:'demo.json',dashboardFilters,runId:'old'})).toBe('/cases?project=demo')
  expect(buildUrl({tab:'load-tests',dashboardFilters,runId:'old'})).toBe('/load-tests')
})
it('normalizes invalid dashboard URL filters and retains API boundary values', () => {
  window.history.replaceState(null,'','/dashboard?days=99&status=unknown&page=1000001&search='+encodeURIComponent('x'.repeat(201)))
  expect(parseLocation().dashboardFilters).toEqual({days:7,status:'',page:1,search:'x'.repeat(200)})
  window.history.replaceState(null,'','/dashboard?days=90&status=timeout&page=1000000')
  expect(parseLocation().dashboardFilters).toEqual({days:90,status:'timeout',page:1000000,search:''})
  for (const page of ['0','-2','1.2','1e3','abc']) {
    window.history.replaceState(null,'','/dashboard?page='+page)
    expect(parseLocation().dashboardFilters.page).toBe(1)
  }
  expect(buildUrl({tab:'dashboard',dashboardFilters:{days:7,page:1,search:' '}})).toBe('/dashboard')
})
