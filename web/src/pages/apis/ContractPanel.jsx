import { useEffect, useRef, useState } from 'react'
import { Field } from '../../components/Field.jsx'
import { api } from '../../utils/studio.js'

export function ContractPanel({ projectRef, project }) {
  const [revisions, setRevisions] = useState([])
  const [baseline, setBaseline] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const sequence = useRef(0)
  useEffect(() => {
    const id = ++sequence.current
    setResult(null); setRevisions([]); setBaseline(''); setError(''); setBusy(false)
    if (projectRef) api(`/api/projects/${encodeURIComponent(projectRef)}/revisions`).then(data => {
      if (sequence.current !== id) return
      setRevisions(data.items || [])
    }).catch(requestError => { if (sequence.current === id) setError(requestError.message) })
    return () => { ++sequence.current }
  }, [projectRef, project?._storage?.revision])
  const check = async () => {
    const id = ++sequence.current
    setBusy(true); setError(''); setResult(null)
    try {
      const data = await api(`/api/projects/${encodeURIComponent(projectRef)}/openapi/contract`, {
        method: 'POST', body: JSON.stringify(baseline ? { baselineRevision: Number(baseline) } : {}),
      })
      if (sequence.current === id) setResult(data)
    } catch (requestError) { if (sequence.current === id) setError(requestError.message) }
    finally { if (sequence.current === id) setBusy(false) }
  }
  return <section className="card" aria-label="OpenAPI 계약 검증">
    <div className="section-header"><h2>OpenAPI 계약 검증</h2><button className="primary" disabled={!projectRef || busy} onClick={check}>{busy ? '검사 중…' : '계약 검사'}</button></div>
    <p className="hint">저장된 명세를 검사합니다. 기준 revision을 선택하면 삭제·필수값·타입·응답 변경도 비교합니다. 불확실한 변경은 검토 대상으로 차단합니다.</p>
    <Field label="비교 기준 revision"><select disabled={busy} value={baseline} onChange={event => { setBaseline(event.target.value); setResult(null) }}><option value="">현재 명세 lint만 검사</option>{revisions.filter(item => item.revision < project?._storage?.revision).map(item => <option key={item.revision} value={item.revision}>revision {item.revision}</option>)}</select></Field>
    {error && <p role="alert" className="notice">{error}</p>}
    {result && <div role="status">
      <h3>{result.compatible ? '계약 검사 통과' : '계약 검사 차단'}</h3>
      <p>현재 revision {result.currentRevision}{result.baselineRevision ? ` / 기준 revision ${result.baselineRevision}` : ''}</p>
      {(result.issues || []).map((item, index) => <p key={`issue-${index}`}>{item.severity === 'warning' ? '경고' : '오류'} · {item.code} · <code>{item.path}</code></p>)}
      {(result.changes || []).map(item => <p key={item.id}>{item.severity === 'review' ? '검토 필요' : '호환성 손상'} · {item.code} · <code>{item.path}</code></p>)}
      {!!result.changes?.length && <p className="hint">승인 예외는 CLI 결과의 변경 ID와 두 명세 해시에 사유·승인자를 기록한 파일로 관리합니다. 이 화면은 승인 권한을 부여하지 않습니다.</p>}
    </div>}
  </section>
}
