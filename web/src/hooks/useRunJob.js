import { useEffect, useRef, useState } from 'react'
import { api } from '../utils/studio.js'

const terminal = new Set(['passed', 'failed', 'error', 'timeout', 'cancelled'])
const remember = (key, id) => { try { sessionStorage.setItem(key, id) } catch { /* Storage can be disabled. */ } }
const restore = key => { try { return sessionStorage.getItem(key) || '' } catch { return '' } }

export function useRunJob(scope) {
  const key = `studio-run:${scope}`
  const [result, setResult] = useState(null)
  const [runId, setRunId] = useState('')
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  const generation = useRef(0)

  useEffect(() => {
    generation.current += 1
    const id = restore(key)
    setRunId(id)
    setResult(id ? { runId: id, status: 'reconnecting' } : null)
    setBusy(Boolean(id))
    return () => { generation.current += 1 }
  }, [key])

  useEffect(() => {
    if (!runId) return
    let disposed = false
    let timer
    const controller = new AbortController()
    const poll = async () => {
      try {
        const job = await api(`/api/runs/${encodeURIComponent(runId)}`, { signal: controller.signal })
        if (disposed) return
        setResult(job)
        setBusy(!terminal.has(job.status))
        if (!terminal.has(job.status)) timer = setTimeout(poll, 700)
      } catch (error) {
        if (disposed) return
        if (error.status === 404) {
          setResult({ runId, error: '실행 조회 기간이 만료되었거나 서버가 재시작되었습니다.' })
          setBusy(false)
          try { sessionStorage.removeItem(key) } catch { /* Optional storage. */ }
        } else {
          setResult(current => ({ ...current, runId, status: current?.status || 'reconnecting', pollError: '연결을 다시 시도하고 있습니다. 실행 작업은 서버에서 계속 진행됩니다.' }))
          timer = setTimeout(poll, 2000)
        }
      }
    }
    poll()
    return () => { disposed = true; clearTimeout(timer); controller.abort() }
  }, [runId, key])

  const start = async body => {
    if (submitting.current || busy) return
    submitting.current = true
    setBusy(true)
    const current = generation.current
    try {
      const job = await api('/api/runs', { method: 'POST', body: JSON.stringify(body) })
      remember(key, job.runId)
      if (generation.current === current) { setResult(job); setRunId(job.runId) }
    } catch (error) {
      if (generation.current === current) { setBusy(false); setResult({ error: error.message }) }
      throw error
    } finally { submitting.current = false }
  }
  const cancel = async () => {
    const current = generation.current
    try {
      const job = await api(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST', body: '{}' })
      if (generation.current === current) { setResult(job); setBusy(!terminal.has(job.status)) }
    } catch (error) {
      if (generation.current === current) setResult(value => ({ ...value, pollError: error.message }))
    }
  }
  return { result, setResult, busy, start, cancel }
}
