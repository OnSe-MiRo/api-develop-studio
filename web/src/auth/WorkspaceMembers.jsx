import { useEffect, useRef, useState } from 'react'
import { api } from '../utils/studio.js'

export function WorkspaceMembers({ onClose, refreshKey = 0 }) {
  const [members, setMembers] = useState([])
  const [events, setEvents] = useState([])
  const [cursor, setCursor] = useState(null)
  const [selected, setSelected] = useState(null)
  const [role, setRole] = useState('viewer')
  const [status, setStatus] = useState('active')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const refreshSequence = useRef(0)
  const refresh = async () => {
    const sequence = ++refreshSequence.current
    try {
      const [people, audit] = await Promise.all([api('/api/workspace/members'), api('/api/workspace/audit')])
      if (sequence === refreshSequence.current) { setMembers(people.items); setEvents(audit.items); setCursor(audit.nextCursor) }
    } catch (failure) { if (sequence === refreshSequence.current) throw failure }
  }
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    refresh().catch(failure => { if (active) setError(failure.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false; refreshSequence.current++ }
  }, [refreshKey])
  const save = async () => {
    setBusy(true); setError('')
    try { await api('/api/workspace/members', { method: 'POST', body: JSON.stringify({ userId: selected.user_id, role, status, reason, revision: selected.version }) }); setSelected(null); setReason(''); await refresh() }
    catch (failure) { setError(failure.status === 409 ? '다른 변경과 충돌했습니다. 새 목록에서 다시 선택하세요.' : failure.message); if (failure.status === 409) { setSelected(null); await refresh() } }
    finally { setBusy(false) }
  }
  const more = async () => {
    const sequence = ++refreshSequence.current
    setBusy(true)
    try { const data = await api(`/api/workspace/audit?before=${encodeURIComponent(cursor)}`); if (sequence === refreshSequence.current) { setEvents(current => [...current, ...data.items]); setCursor(data.nextCursor) } }
    catch (failure) { if (sequence === refreshSequence.current) setError(failure.message) }
    finally { setBusy(false) }
  }
  return <main className="project-page editor identity-management">
    <div className="section-header identity-heading">
      <h1>Workspace 멤버·감사 기록</h1>
      <button className="ghost" onClick={onClose}>돌아가기</button>
    </div>
    {error && <p role="alert" className="notice">{error}</p>}
    {loading && <p role="status" className="hint">멤버와 감사 기록을 불러오는 중입니다…</p>}
    <div className="identity-grid">
      <section className="card member-panel" aria-labelledby="workspace-members-title">
        <div className="section-header"><h2 id="workspace-members-title">멤버 <span className="count">{members.length}</span></h2></div>
        <p className="hint">멤버를 선택해 역할과 상태를 변경하세요. 계정의 최초 연결은 서버 운영자가 수행합니다.</p>
        <div className="member-list">{members.map(member => <button className="ghost member-item" key={member.user_id} aria-label={`${member.display_name} · ${member.role} · ${member.status}`} aria-pressed={selected?.user_id === member.user_id} disabled={busy || loading} onClick={() => { setSelected(member); setRole(member.role); setStatus(member.status); setReason('') }}><strong>{member.display_name}</strong><span>{member.role} · {member.status}</span></button>)}</div>
        {!loading && !error && !members.length && <p className="empty compact">표시할 멤버가 없습니다.</p>}
        {selected && <div className="member-edit">
          <h3>{selected.display_name}</h3>
          <div className="member-fields">
            <label className="field">역할<select value={role} disabled={busy || loading} onChange={e => setRole(e.target.value)}>{['owner', 'admin', 'editor', 'runner', 'viewer'].map(item => <option key={item}>{item}</option>)}</select></label>
            <label className="field">상태<select value={status} disabled={busy || loading} onChange={e => setStatus(e.target.value)}><option value="active">활성</option><option value="disabled">비활성</option></select></label>
          </div>
          <label className="field">변경 사유<textarea rows={3} value={reason} maxLength={2000} disabled={busy || loading} onChange={e => setReason(e.target.value)} /></label>
          <p className="hint">Owner 변경은 Owner만 가능하며 마지막 Owner는 제거할 수 없습니다.</p>
          <div className="actions"><button className="primary" disabled={busy || loading || !reason.trim()} onClick={save}>membership 변경 저장</button><button className="ghost" disabled={busy} onClick={() => { setSelected(null); setReason('') }}>취소</button></div>
        </div>}
      </section>
      <section className="card audit-panel" aria-labelledby="workspace-audit-title">
        <div className="section-header"><h2 id="workspace-audit-title">감사 기록</h2><span className="hint">최근 기록부터 표시</span></div>
        {!loading && !error && !events.length && <p className="empty compact">아직 감사 기록이 없습니다.</p>}
        <div className="audit-list">{events.map(event => <article className="audit-event" key={event.id}>
          <strong>{event.action}</strong><p className="hint">{event.actor_id || '시스템'} · <time>{event.created_at}</time></p><code>{event.target}</code>
          <details><summary>변경 상세</summary><pre>{JSON.stringify(event.detail, null, 2)}</pre></details>
        </article>)}</div>
        {cursor && <button className="ghost audit-more" disabled={busy || loading} onClick={more}>이전 감사 기록 더 보기</button>}
      </section>
    </div>
  </main>
}
