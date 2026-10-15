import { useEffect, useRef, useState } from 'react'
import { Field } from '../../components/Field.jsx'
import { api } from '../../utils/studio.js'

const labels = { draft: '초안', published: '발행', deprecated: '사용 중단 예정', retired: '폐기' }
const transitions = { draft: ['published', 'retired'], published: ['deprecated', 'retired'], deprecated: ['retired'], retired: [] }

function ProjectReleasePanel({ projectRef, project }) {
  const [items, setItems] = useState([])
  const [cursor, setCursor] = useState(null)
  const [selected, setSelected] = useState(null)
  const [source, setSource] = useState(null)
  const [version, setVersion] = useState('')
  const [notes, setNotes] = useState('')
  const [baseline, setBaseline] = useState('')
  const [reason, setReason] = useState('')
  const [state, setState] = useState('published')
  const [acknowledge, setAcknowledge] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sequence = useRef(0)
  const base = `/api/projects/${encodeURIComponent(projectRef)}/releases`
  const readOnly = projectRef === 'example-api.json'
  const hasSnapshot = Boolean(project?.docs_bundle || project?.docs_file?.document)
  const choose = value => {
    setSelected(value); setSource(null); setReason(''); setAcknowledge(false)
    setState(transitions[value.state]?.[0] || '')
  }
  const list = async (before = null) => {
    const data = await api(base + (before ? `?before=${encodeURIComponent(before)}` : ''))
    setItems(previous => before ? [...previous, ...data.items] : data.items); setCursor(data.nextCursor)
  }
  useEffect(() => {
    let active = true
    setBusy(true)
    api(base).then(data => { if (active) { setItems(data.items); setCursor(data.nextCursor) } })
      .catch(requestError => { if (active) setError(requestError.message) })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false; ++sequence.current }
  }, [base])
  const perform = async action => {
    const current = ++sequence.current
    setBusy(true); setError('')
    try { await action(current) }
    catch (requestError) { if (current === sequence.current) setError(requestError.message) }
    finally { if (current === sequence.current) setBusy(false) }
  }
  const open = id => perform(async current => {
    const detail = await api(`${base}/${encodeURIComponent(id)}`)
    if (current === sequence.current) choose(detail)
  })
  const create = () => perform(async current => {
    const detail = await api(base, { method: 'POST', body: JSON.stringify({ version, notes, projectRevision: project._storage.revision, baselineId: baseline || null }) })
    if (current === sequence.current) { choose(detail); setVersion(''); setNotes(''); await list() }
  })
  const transition = () => perform(async current => {
    const detail = await api(`${base}/${encodeURIComponent(selected.id)}/transition`, { method: 'POST', body: JSON.stringify({ state, revision: selected.revision, reason, acknowledgeChanges: acknowledge }) })
    if (current === sequence.current) { choose(detail); await list() }
  })
  const loadSource = () => perform(async current => {
    const result = await api(`${base}/${encodeURIComponent(selected.id)}/source`)
    if (current === sequence.current) setSource(result)
  })
  return <section className="card release-panel" aria-label="API 릴리스 관리">
    <div className="section-header"><h2>API 릴리스</h2><button className="ghost" disabled={busy} onClick={() => perform(() => list())}>릴리스 새로고침</button></div>
    <p className="hint">저장된 명세 revision을 고정합니다. 발행은 이 Workspace의 릴리스 상태 변경이며 외부 공개나 배포를 자동으로 수행하지 않습니다.</p>
    {!readOnly && <details><summary>릴리스 초안 만들기</summary>
      {!hasSnapshot && <p className="notice">프로젝트에 OpenAPI 파일 또는 bundle을 먼저 저장하세요. URL만 등록한 명세는 고정할 수 없습니다.</p>}
      <Field label="릴리스 버전"><input value={version} disabled={busy} onChange={e => setVersion(e.target.value)} placeholder="1.0.0" /></Field>
      <Field label="변경 설명"><textarea rows={4} value={notes} maxLength={20000} disabled={busy} onChange={e => setNotes(e.target.value)} /></Field>
      <Field label="기준 릴리스"><select value={baseline} disabled={busy} onChange={e => setBaseline(e.target.value)}><option value="">최근 발행 릴리스 자동 선택</option>{items.filter(item => ['published', 'deprecated'].includes(item.state)).map(item => <option key={item.id} value={item.id}>{item.version} · revision {item.projectRevision}</option>)}</select></Field>
      <button className="primary" disabled={busy || !hasSnapshot || !project?._storage?.revision || !version.trim()} onClick={create}>현재 revision으로 초안 생성</button>
    </details>}
    {!items.length && !busy && <p className="empty">등록된 릴리스가 없습니다.</p>}
    <div className="release-list">{items.map(item => <button key={item.id} className={selected?.id === item.id ? 'primary' : 'ghost'} disabled={busy} onClick={() => open(item.id)}>{item.version} · {labels[item.state]} · 명세 revision {item.projectRevision}</button>)}</div>
    {cursor && <button className="ghost" disabled={busy} onClick={() => perform(() => list(cursor))}>이전 릴리스 더 보기</button>}
    {selected && <div className="release-detail" aria-label="선택한 릴리스">
      <h3>{selected.version} · {labels[selected.state]}</h3>
      <p>명세 revision {selected.projectRevision} · 릴리스 revision {selected.revision}</p>
      <p>원본 지문 <code>{selected.sourceDigest}</code></p>
      <p>비교 기준 {selected.baselineId || '첫 릴리스'}</p>
      <pre>{selected.notes || '변경 설명 없음'}</pre>
      <h4>Operation 변경 로그</h4>
      {(selected.comparison?.operationChanges || []).map(change => <p key={`${change.method}-${change.path}`}>{({ added: '추가', removed: '삭제', changed: '수정', deprecated: '사용 중단 예정', restored: '사용 중단 표시 해제' })[change.kind]} · {change.method} <code>{change.path}</code></p>)}
      <h4>호환성 변경</h4>
      {!selected.comparison?.changes?.length && <p className="hint">{selected.baselineId ? '비교 기준 대비 감지된 계약 변경 없음' : '첫 릴리스이므로 호환성 비교 기준이 없습니다.'}</p>}
      {(selected.comparison?.changes || []).map(change => <p key={change.id}>{change.severity} · {change.code} · <code>{change.path}</code></p>)}
      {(selected.comparison?.issues || []).map((issue, index) => <p key={index}>{issue.severity} · {issue.code} · <code>{issue.path}</code></p>)}
      <h4>사용 중단 예정 operation</h4>
      {selected.deprecatedOperations?.length ? selected.deprecatedOperations.map(item => <p key={`${item.method}-${item.path}`}>{item.method} <code>{item.path}</code> · deprecated</p>) : <p className="hint">없음</p>}
      <button className="ghost" disabled={busy} onClick={loadSource}>고정된 명세 원본 보기</button>
      {source && <pre aria-label="고정된 명세 원본">{JSON.stringify(source, null, 2)}</pre>}
      {!readOnly && transitions[selected.state]?.length > 0 && <div className="release-transition">
        <p className="hint">Owner/Admin만 전환할 수 있습니다. 발행 후에는 원본과 버전을 수정하지 않습니다.</p>
        <Field label="변경할 릴리스 상태"><select value={state} disabled={busy} onChange={e => { setState(e.target.value); setAcknowledge(false) }}>{transitions[selected.state].map(value => <option key={value} value={value}>{labels[value]}</option>)}</select></Field>
        <Field label="승인·전환 사유"><textarea rows={2} value={reason} maxLength={2000} disabled={busy} onChange={e => setReason(e.target.value)} /></Field>
        {state === 'published' && !!selected.comparison?.changes?.length && <label><input type="checkbox" checked={acknowledge} disabled={busy} onChange={e => setAcknowledge(e.target.checked)} />호환성 변경을 검토하고 승인합니다</label>}
        <button className="primary" disabled={busy || !reason.trim() || (state === 'published' && !!selected.comparison?.changes?.length && !acknowledge)} onClick={transition}>릴리스 상태 변경</button>
      </div>}
      <h4>승인·변경 이력</h4>
      <ol>{(selected.events || []).map(event => <li key={event.revision}>{labels[event.to_state]} · {event.actor_id} · {event.created_at}{event.acknowledge_changes ? ' · 호환성 변경 승인' : ''}<p>{event.reason}</p></li>)}</ol>
    </div>}
    {error && <p role="alert" className="notice">{error} 충돌한 경우 릴리스를 다시 선택해 최신 상태를 확인하세요.</p>}
  </section>
}

export function ReleasePanel(props) {
  return <ProjectReleasePanel key={props.projectRef} {...props} />
}
