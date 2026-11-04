import { afterEach, expect, it, vi } from 'vitest'
import { authenticatedFetch, configureSession, jobNamespace } from './session.js'
afterEach(() => { configureSession(null); vi.unstubAllGlobals() })
it('adds CSRF only to authenticated mutation requests and scopes job IDs', async () => {
  const fetch = vi.fn().mockResolvedValue({ status: 200 }); vi.stubGlobal('fetch', fetch)
  configureSession({ authenticated: true, mode: 'remote', userId: 'alice', workspace: { id: 'a' }, csrfToken: 'csrf-secret' })
  expect(jobNamespace()).toBe('alice:a:')
  await authenticatedFetch('/api/request', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
  expect(fetch.mock.calls[0][1].headers.get('X-CSRF-Token')).toBe('csrf-secret')
  await authenticatedFetch('/api/projects')
  expect(fetch.mock.calls[1][1].headers.get('X-Studio-Workspace')).toBe('a')
  expect(fetch.mock.calls[1][1].headers.has('X-CSRF-Token')).toBe(false)
  configureSession({ authenticated: true, mode: 'remote', userId: 'alice', workspace: { id: 'b' }, csrfToken: 'other' })
  expect(jobNamespace()).toBe('alice:b:')
})
it('preserves local request options and never persists credentials', async () => {
  const fetch = vi.fn().mockResolvedValue({ status: 200 }); vi.stubGlobal('fetch', fetch)
  configureSession({ authenticated: true, mode: 'local', userId: 'local-user' })
  const options = { method: 'POST', body: 'test' }; await authenticatedFetch('/api/request', options)
  expect(fetch).toHaveBeenCalledWith('/api/request', options)
  expect(jobNamespace()).toBe('')
})

it('never sends Studio CSRF or workspace headers to another origin', async () => {
  const fetch = vi.fn().mockResolvedValue({ status: 200 }); vi.stubGlobal('fetch', fetch)
  configureSession({ authenticated: true, mode: 'remote', userId: 'alice', workspace: { id: 'a' }, csrfToken: 'csrf-secret' })
  await authenticatedFetch('https://outside.example.test/api/request', { method: 'POST', body: '{}' })
  expect(fetch.mock.calls[0][1]).toEqual({ method: 'POST', body: '{}' })
})
