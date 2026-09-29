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
