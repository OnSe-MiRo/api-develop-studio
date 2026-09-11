import { useEffect, useState } from 'react'
import { api } from '../utils/studio.js'

export function OwnershipPanel({ projectReference }) {
  const [state, setState] = useState(null)
  const [url, setUrl] = useState('')
  const [issued, setIssued] = useState(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [grantUrl, setGrantUrl] = useState('')
  const [method, setMethod] = useState('POST')
  const [approvalKey, setApprovalKey] = useState('')
  const query = `?project=${encodeURIComponent(projectReference)}`
  const refresh = async () => setState(await api(`/api/ownership${query}`))
  useEffect(() => { setIssued(null); setState(null); refresh().catch(e => setNotice(e.message)) }, [projectReference])
  const action = async (name, body) => {
    setBusy(true); setNotice('')
    try {
      const data = await api(`/api/ownership/${name}${query}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Studio-Approver-Key': approvalKey }, body: JSON.stringify(body) })
      if (name === 'issue') setIssued(data)
      if (name === 'verify') setIssued(null)
      setNotice(name === 'verify' ? '소유권 확인이 완료되었습니다.' : '처리되었습니다.')
      await refresh()
    } catch (e) { setNotice(e.message) }
    finally { setBusy(false) }
  }
  const labels = { pending: '확인 대기', verified: '확인됨', expired: '만료됨', revoked: '인증 취소됨' }
  return <section className="card ownership-panel">
    <h2>API 소유권 확인</h2>
    <p>{state?.skip_verification ? '로컬 모드 · 소유권 확인 생략' : '소유권 확인 필수 · 30일 미사용 또는 90일 경과 시 재인증'}</p>
    <p className="hint">프로젝트 Base URL을 먼저 저장하세요. 공개 HTTPS 서버에 검증 응답을 배포해야 합니다. API 요청 인증정보는 별도로 설정합니다.</p>
    <label className="field"><span>검증할 저장된 Base URL</span><input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://api.example.com" /></label>
    <button className="primary" disabled={busy || !url} onClick={() => action('issue', { url })}>검증 토큰 발급 / 재발급</button>
    {issued && <div><p>아래 URL에 JSON을 배포한 뒤 확인하세요. 토큰은 이 화면에서만 표시됩니다.</p><pre>{issued.verification_url}</pre><pre>{JSON.stringify({ challenge: issued.challenge }, null, 2)}</pre><p>만료: {new Date(issued.expires_at * 1000).toLocaleString()}</p><button className="ghost" onClick={() => navigator.clipboard.writeText(JSON.stringify({ challenge: issued.challenge })).then(() => setNotice('복사했습니다.')).catch(() => setNotice('복사할 수 없습니다. 위 내용을 직접 복사하세요.'))}>응답 JSON 복사</button></div>}
    {state?.proofs.map(proof => <div className="ownership-record" key={proof.id}><strong>{proof.origin}</strong><span>{labels[proof.state] || proof.state} · {new Date(proof.expires_at * 1000).toLocaleString()}</span>{proof.state === 'pending' && <button disabled={busy} className="ghost" onClick={() => action('verify', { verification_id: proof.id })}>소유자 확인</button>}</div>)}
    <h3>외부 Setup 1회 호출 승인</h3>
    <p className="hint">정확한 HTTPS URL과 메서드에만 적용됩니다. Query 없는 URL을 등록하세요. 재시도·redirect 없이 호출하며 동일 대상은 60초 간격으로 제한합니다.</p>
    <label className="field"><span>외부 호출 URL</span><input value={grantUrl} onChange={e => setGrantUrl(e.target.value)} placeholder="https://auth.example.com/token" /></label>
    <label className="field"><span>HTTP 메서드</span><select value={method} onChange={e => setMethod(e.target.value)}>{['GET','POST','HEAD','PUT','PATCH','DELETE','OPTIONS'].map(m => <option key={m}>{m}</option>)}</select></label>
    {!state?.local_server && <label className="field"><span>서버 운영자 승인 키</span><input type="password" autoComplete="off" value={approvalKey} onChange={e => setApprovalKey(e.target.value)} /></label>}
    <button className="ghost" disabled={busy || !grantUrl} onClick={() => action('grant', { url: grantUrl, method })}>외부 호출 승인</button>
    {state?.grants.map(grant => <div className="ownership-record" key={grant.method + grant.url}><span>{grant.method} {grant.url}</span><button className="danger-button" disabled={busy} onClick={() => action('remove-grant', grant)}>승인 취소</button></div>)}
    <p role="status">{notice}</p>
  </section>
}
