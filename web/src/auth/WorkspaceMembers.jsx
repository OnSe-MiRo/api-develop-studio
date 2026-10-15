import { useEffect, useState } from 'react'
import { api } from '../utils/studio.js'

export function WorkspaceMembers({ onClose }) {
  const [members, setMembers] = useState([])
  const [events, setEvents] = useState([])
  const [cursor, setCursor] = useState(null)
  const [selected, setSelected] = useState(null)
  const [role, setRole] = useState('viewer')
  const [status, setStatus] = useState('active')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const refresh = async () => {
    const [people, audit] = await Promise.all([api('/api/workspace/members'), api('/api/workspace/audit')])
    setMembers(people.items); setEvents(audit.items); setCursor(audit.nextCursor)
  }
  useEffect(() => { let active = true; refresh().catch(failure => { if (active) setError(failure.message) }); return () => { active = false } }, [])
  const save = async () => {
    setBusy(true); setError('')
    try { await api('/api/workspace/members', { method: 'POST', body: JSON.stringify({ userId: selected.user_id, role, status, reason, revision: selected.version }) }); setSelected(null); setReason(''); await refresh() }
    catch (failure) { setError(failure.status === 409 ? '다른 변경과 충돌했습니다. 새 목록에서 다시 선택하세요.' : failure.message); if (failure.status === 409) { setSelected(null); await refresh() } }
    finally { setBusy(false) }
  }
  const more = async () => {
    setBusy(true)
    try { const data = await api(`/api/workspace/audit?before=${encodeURIComponent(cursor)}`); setEvents(current => [...current, ...data.items]); setCursor(data.nextCursor) }
    catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <main className="editor"><section className="card identity-management"><div className="section-header"><h1>Workspace 멤버·감사 기록</h1><button className="ghost" onClick={onClose}>돌아가기</button></div><p className="hint">계정과 issuer/subject의 최초 연결은 서버 운영자가 수행합니다. 여기서는 현재 Workspace의 기존 membership을 관리합니다.</p>
    <div className="member-list">{members.map(member => <button className="ghost" key={member.user_id} disabled={busy} onClick={() => { setSelected(member); setRole(member.role); setStatus(member.status); setReason('') }}>{member.display_name} · {member.role} · {member.status}</button>)}</div>
    {selected && <div className="member-edit"><h2>{selected.display_name}</h2><label>역할<select value={role} disabled={busy} onChange={e => setRole(e.target.value)}>{['owner', 'admin', 'editor', 'runner', 'viewer'].map(item => <option key={item}>{item}</option>)}</select></label><label>상태<select value={status} disabled={busy} onChange={e => setStatus(e.target.value)}><option value="active">활성</option><option value="disabled">비활성</option></select></label><label>변경 사유<textarea value={reason} maxLength={2000} disabled={busy} onChange={e => setReason(e.target.value)} /></label><p className="hint">Owner 변경은 Owner만 가능하며 마지막 Owner는 제거할 수 없습니다.</p><button className="primary" disabled={busy || !reason.trim()} onClick={save}>membership 변경 저장</button></div>}
    <h2>감사 기록</h2>{events.map(event => <article className="audit-event" key={event.id}><strong>{event.action}</strong><p>{event.actor_id || '시스템'} · {event.created_at}</p><code>{event.target}</code><pre>{JSON.stringify(event.detail, null, 2)}</pre></article>)}{cursor && <button className="ghost" disabled={busy} onClick={more}>이전 감사 기록 더 보기</button>}{error && <p role="alert" className="notice">{error}</p>}
  </section></main>
}
