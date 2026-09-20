import { useEffect, useState } from 'react'
import { api } from '../../utils/studio.js'

export function CoveragePanel({ projectRef, revision }) {
  const [data, setData] = useState(null)
  const [preview, setPreview] = useState(null)
  const [fields, setFields] = useState([])
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const endpoint = `/api/projects/${encodeURIComponent(projectRef)}/openapi/coverage`
  const request = body => api(endpoint, { method: 'POST', body: JSON.stringify(body) })
  const load = async () => { try { setData(await request({})); setNotice('') } catch (error) { setNotice(error.message) } }
  useEffect(() => { setData(null); setPreview(null); let active = true; if (projectRef) request({}).then(value => { if (active) setData(value) }).catch(error => { if (active) setNotice(error.message) }); return () => { active = false } }, [projectRef, revision])
  const inspect = async reference => { setBusy(true); try { setPreview({ ...await request({ case: reference }), reference }); setFields([]); setNotice('') } catch (error) { setNotice(error.message) } finally { setBusy(false) } }
  const apply = async () => { setBusy(true); try { await request({ case: preview.reference, apply: true, fields, caseRevision: preview.caseRevision, projectRevision: preview.projectRevision }); setPreview(null); await load(); setNotice('선택한 필드와 명세 연결 기준을 저장했습니다.') } catch (error) { setNotice(error.message) } finally { setBusy(false) } }
  const responses = data?.operations.flatMap(op => op.responses) || []
  return <section className="card"><div className="section-header"><h2>명세–케이스 커버리지</h2><button className="ghost" onClick={load}>새로고침</button></div><p className="hint">연결 응답 {responses.filter(row => row.cases.length).length} / {responses.length} · assertion, body, 인증과 secret은 동기화 시 보존합니다. 최근 성공은 저장된 케이스의 실행 결과입니다.</p>{data?.operations.map(op => <article key={op.id}><h3>{op.id} · 케이스 {op.cases.length}개</h3><p>Operation 최근 성공: {op.lastSuccess || '기록 없음'}</p>{op.responses.map(row => <p key={row.status}><strong>{row.status}</strong> · {row.cases.length ? `${row.cases.length}개 연결` : '미검증 응답'} · 최근 성공: {row.lastSuccess || '기록 없음'}</p>)}{op.cases.map(item => <p key={item.reference}><code>{item.reference}</code> · {item.linked ? item.changed ? '명세 변경 감지' : '명세 일치' : '연결 기준 미등록'} <button className="ghost" disabled={busy} onClick={() => inspect(item.reference)}>변경 미리보기</button></p>)}</article>)}{!!data?.unlinked.length && <p role="status">연결되지 않은 케이스: {data.unlinked.join(', ')} (operation 삭제 또는 요청 경로 확인 필요)</p>}{preview && <div><h3>변경 미리보기 · {preview.reference}</h3><p>수정한 값은 유지됩니다. 선택하지 않은 필드도 유지되며 현재 명세를 새 비교 기준으로 저장합니다.</p>{preview.changes.map(change => <label key={change.field} style={{ display: 'block' }}><input type="checkbox" disabled={!change.selectable} checked={fields.includes(change.field)} onChange={event => setFields(current => event.target.checked ? [...current, change.field] : current.filter(field => field !== change.field))} />{change.field}: {JSON.stringify(change.before)} → {JSON.stringify(change.after)} {change.reason}</label>)}{!preview.changes.length && <p>자동 변경 가능한 필드가 없습니다. body와 assertion은 케이스 편집기에서 검토하세요.</p>}<button className="primary" disabled={busy || projectRef === 'example-api.json'} onClick={apply}>선택 필드 및 연결 기준 저장</button><button className="ghost" onClick={() => setPreview(null)}>닫기</button></div>}{notice && <p role="status">{notice}</p>}</section>
}
