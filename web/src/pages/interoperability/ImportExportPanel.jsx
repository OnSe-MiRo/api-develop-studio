import { useRef, useState } from 'react'
import { api } from '../../utils/studio.js'

export function ImportExportPanel({ projectRef, caseItems, refresh }) {
  const [format, setFormat] = useState('curl')
  const [source, setSource] = useState('')
  const [tag, setTag] = useState('imported')
  const [preview, setPreview] = useState(null)
  const [overwrite, setOverwrite] = useState({})
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [reference, setReference] = useState('')
  const [exported, setExported] = useState(null)
  const sequence = useRef(0)
  const edit = (setter, value) => {
    sequence.current += 1; setter(value); setPreview(null); setOverwrite({}); setNotice('')
  }
  const body = () => ({ project: projectRef, format, source, tag })
  const readFile = async event => {
    const file = event.target.files?.[0]
    if (!file) return
    const current = ++sequence.current
    setPreview(null); setOverwrite({})
    if (file.size > 1024 * 1024) { setNotice('파일은 1 MiB 이하여야 합니다.'); return }
    try { const text = await file.text(); if (current === sequence.current) { setSource(text); setNotice('') } }
    catch { if (current === sequence.current) setNotice('파일을 읽지 못했습니다.') }
  }
  const inspect = async () => {
    const current = ++sequence.current
    setBusy(true); setNotice(''); setPreview(null); setOverwrite({})
    try { const result = await api('/api/interoperability/preview', { method: 'POST', body: JSON.stringify(body()) }); if (current === sequence.current) setPreview(result) }
    catch (error) { if (current === sequence.current) setNotice(error.message) }
    finally { setBusy(false) }
  }
  const save = async item => {
    setBusy(true); setNotice('')
    try {
      const result = await api('/api/interoperability/apply', { method: 'POST', body: JSON.stringify({ ...body(), index: item.index, digest: item.digest, overwrite: Boolean(overwrite[item.digest]) }) })
      setNotice(`저장 완료: ${result.reference} · revision ${result.revision}`)
      setPreview(null); setOverwrite({}); await refresh()
    } catch (error) { setNotice(error.message); setPreview(null) }
    finally { setBusy(false) }
  }
  const exportCase = async () => {
    setBusy(true); setNotice(''); setExported(null)
    try { setExported(await api('/api/interoperability/curl', { method: 'POST', body: JSON.stringify({ reference }) })) }
    catch (error) { setNotice(error.message) }
    finally { setBusy(false) }
  }
  const items = preview?.environment ? [preview.environment] : preview?.items || []
  return <section className="card interoperability-panel" aria-label="가져오기·내보내기">
    <h2>가져오기·내보내기</h2>
    <p className="hint">원본 명령이나 스크립트는 실행하지 않습니다. 민감값 후보를 제거한 미리보기를 검토하고 항목별로 저장하세요. 가져온 요청의 예상 상태는 200이며 실행 전에 수정할 수 있습니다.</p>
    <label>가져오기 형식<select value={format} disabled={busy} onChange={e => edit(setFormat, e.target.value)}><option value="curl">cURL</option><option value="postman">Postman Collection v2</option><option value="environment">Postman Environment</option><option value="har">HAR</option></select></label>
    {format !== 'environment' && <label>저장 태그<input value={tag} maxLength={60} disabled={busy} onChange={e => edit(setTag, e.target.value)} /><small>새 가져오기 묶음은 다른 태그를 사용하세요. 소문자·숫자·_·-를 사용할 수 있습니다.</small></label>}
    <label>원본 파일 (최대 1 MiB)<input type="file" accept=".json,.har,.txt" disabled={busy} onChange={readFile} /></label>
    <label>가져올 원본<textarea value={source} rows={8} disabled={busy} onChange={e => edit(setSource, e.target.value)} placeholder="cURL 명령 또는 JSON을 붙여넣으세요." /></label>
    <button className="primary" disabled={busy || !source.trim()} onClick={inspect}>가져오기 미리보기</button>
    {preview && <div aria-label="가져오기 미리보기 결과">
      {preview.warnings.map(message => <p className="notice" key={message}>{message}</p>)}
      {items.map(item => <article className="import-preview-item" key={item.digest}>
        <strong>{item.reference || `환경: ${item.name}`}</strong>
        {preview.environment && <p className="hint">프로젝트 기본 URL을 사용하는 named environment에 변수를 병합합니다. 기본 환경 선택과 기존 secret은 유지합니다.</p>}
        <pre>{JSON.stringify(item.document || item.plain, null, 2)}</pre>
        {item.blocked ? <p role="alert">다른 프로젝트 또는 기존 secret과 충돌하여 저장할 수 없습니다.</p> : <>
          {item.conflict && <label><input type="checkbox" checked={Boolean(overwrite[item.digest])} disabled={busy} onChange={e => setOverwrite({ ...overwrite, [item.digest]: e.target.checked })} />기존 항목 덮어쓰기 확인</label>}
          <button className="primary" disabled={busy || (item.conflict && !overwrite[item.digest])} onClick={() => save(item)}>이 항목 저장</button>
        </>}
      </article>)}
      <p className="hint">저장 후 나머지 항목은 미리보기를 다시 확인하세요. 기존 케이스를 덮어쓰면 요청과 검증 설정이 교체됩니다.</p>
    </div>}
    <h3>cURL 내보내기</h3>
    <label>내보낼 케이스<select value={reference} disabled={busy} onChange={e => { setReference(e.target.value); setExported(null) }}><option value="">케이스 선택</option>{caseItems.map(item => <option key={item} value={item}>{item}</option>)}</select></label>
    <button className="ghost" disabled={busy || !caseItems.includes(reference)} onClick={exportCase}>cURL 생성</button>
    {exported && <>{exported.warnings.map(message => <p className="notice" key={message}>{message}</p>)}<label>내보낸 cURL<textarea readOnly rows={5} value={exported.curl} /></label></>}
    {notice && <p className="notice" role="status">{notice}</p>}
  </section>
}
