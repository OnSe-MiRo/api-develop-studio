import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRunJob } from './useRunJob.js'
import { api } from '../utils/studio.js'

vi.mock('../utils/studio.js', () => ({ api: vi.fn() }))
beforeEach(() => { sessionStorage.clear(); vi.useFakeTimers(); api.mockReset() })
afterEach(() => { vi.useRealTimers() })

describe('async execution', () => {
  it('submits once and follows the job until completion', async () => {
    let polls = 0
    api.mockImplementation(async path => path === '/api/runs' ? { runId: 'one', status: 'queued' } : { runId: 'one', status: ++polls === 1 ? 'running' : 'passed' })
    const { result } = renderHook(() => useRunJob('case'))
    await act(async () => { await Promise.all([result.current.start({}), result.current.start({})]) })
    expect(api.mock.calls.filter(([path]) => path === '/api/runs')).toHaveLength(1)
    expect(result.current.busy).toBe(true)
    await act(async () => { await vi.advanceTimersByTimeAsync(700) })
    expect(result.current.result.status).toBe('passed')
    expect(result.current.busy).toBe(false)
    expect(sessionStorage.getItem('studio-run:case')).toBe('one')
  })

  it('restores a run after remount and sends explicit cancellation', async () => {
    sessionStorage.setItem('studio-run:case', 'existing')
    let cancelled = false
    api.mockImplementation(async path => {
      if (path.endsWith('/cancel')) { cancelled = true; return { runId: 'existing', status: 'cancelling' } }
      return { runId: 'existing', status: cancelled ? 'cancelled' : 'running' }
    })
    const { result, unmount } = renderHook(() => useRunJob('case'))
    await act(async () => {})
    expect(result.current.result.status).toBe('running')
    await act(async () => { await result.current.cancel() })
    await act(async () => { await vi.advanceTimersByTimeAsync(700) })
    expect(result.current.result.status).toBe('cancelled')
    expect(result.current.busy).toBe(false)
    unmount()
    expect(api.mock.calls.filter(([path]) => path.endsWith('/cancel'))).toHaveLength(1)
    expect(api.mock.calls.some(([path]) => path === '/api/runs')).toBe(false)
  })

  it('retries connection errors and allows a new run after an expired id', async () => {
    sessionStorage.setItem('studio-run:case', 'expired')
    api.mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(Object.assign(new Error('missing'), { status: 404 }))
    const { result } = renderHook(() => useRunJob('case'))
    await act(async () => {})
    expect(result.current.result.pollError).toContain('다시 시도')
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(result.current.busy).toBe(false)
    expect(result.current.result.error).toContain('만료')
    expect(sessionStorage.getItem('studio-run:case')).toBe(null)
  })
})
