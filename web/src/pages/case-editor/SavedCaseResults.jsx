import { useEffect, useState } from 'react'
import { api } from '../../utils/studio.js'
import { RunResult } from '../../components/RunResult.jsx'

const terminal = new Set(['passed', 'failed', 'error', 'timeout', 'cancelled'])

export function SavedCaseResults({ projectRef, caseReference, result }) {
  const [items, setItems] = useState([])
  const [revision, setRevision] = useState(0)
  const [selectedRun, setSelectedRun] = useState('')
  const [savedResult, setSavedResult] = useState(null)
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let disposed = false
    setItems([]); setSelectedRun(''); setSavedResult(null); setError(''); setLoading(true)
    const query = new URLSearchParams({ project: projectRef, caseReference })
    api(`/api/saved-results?${query}`).then(data => {
      if (!disposed) setItems(data.items || [])
    }).catch(error => { if (!disposed) setError(error.message) })
      .finally(() => { if (!disposed) setLoading(false) })
    return () => { disposed = true }
  }, [projectRef, caseReference, revision])

  useEffect(() => {
    let disposed = false
    setSavedResult(null)
    if (selectedRun) api(`/api/saved-results/${encodeURIComponent(selectedRun)}`).then(data => {
      if (!disposed) setSavedResult(data)
    }).catch(error => { if (!disposed) setError(error.message) })
    return () => { disposed = true }
  }, [selectedRun])

  const save = async () => {
    setSaving(true); setNotice('')
    try {
      const saved = await api(`/api/runs/${encodeURIComponent(result.runId)}/save`, { method: 'POST' })
      setNotice(`앱에 저장했습니다: ${saved.caseReference} · ${saved.runId}`)
      setRevision(value => value + 1)
    } catch (error) { setNotice(error.message) }
    finally { setSaving(false) }
  }

  return <section className="card">
    <div className="section-header"><h2>저장한 실행 결과</h2>
      {result?.runId && terminal.has(result.status) && <button onClick={save} disabled={saving}>{saving ? '저장 중…' : '실행 결과 앱에 저장'}</button>}
    </div>
    <p className="hint">현재 계정으로 저장한 이 케이스의 최근 100개 결과입니다. 요청·응답과 실행 로그를 보관하며, 새로고침 후에도 다시 열 수 있습니다. 인증값과 보안 변수는 마스킹됩니다.</p>
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    {loading ? <p>저장 결과 불러오는 중…</p> : !items.length && !error ? <p>저장한 실행 결과가 없습니다.</p> : null}
    {items.length > 0 && <label className="field"><span>저장 결과 선택</span><select value={selectedRun} onChange={event => { setError(''); setSelectedRun(event.target.value) }}>
      <option value="">결과를 선택하세요.</option>
      {items.map(item => <option value={item.runId} key={item.runId}>{new Date(item.savedAt).toLocaleString()} · {item.status} · {item.runId}</option>)}
    </select></label>}
    {savedResult && <RunResult result={savedResult} />}
  </section>
}
