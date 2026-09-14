import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildUrl, navigateTo, parseLocation, restoreJson, stripJson } from './router.js'

describe('router', () => {
  beforeEach(() => window.history.replaceState(null, '', '/'))

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
})
