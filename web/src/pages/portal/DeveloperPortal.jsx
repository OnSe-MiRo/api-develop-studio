import { authenticatedFetch } from '../../auth/session.js'
import { useEffect, useMemo, useRef, useState } from 'react'
import { AuthorSidebar } from '../../components/ProjectSidebar.jsx'
import { Field } from '../../components/Field.jsx'
import { useRunJob } from '../../hooks/useRunJob.js'
import { api } from '../../utils/studio.js'
import { examples, operations, resolve, searchOperations, servers } from './document.js'

const languages = [['python', 'Python'], ['javascript', 'JavaScript'], ['typescript', 'TypeScript'], ['java', 'Java'], ['kotlin', 'Kotlin'], ['go', 'Go'], ['csharp', 'C#']]
const statuses = { queued: '대기 중', running: '생성 중', cancelling: '취소 중', reconnecting: '작업 다시 조회 중', passed: 'SDK 보존 완료', failed: '생성 실패', error: '생성 오류', cancelled: '취소됨', timeout: '시간 초과' }
const json = value => JSON.stringify(value, null, 2)

function MediaExamples({ document, content }) {
  const types = Object.keys(content || {})
  const [selected, setSelected] = useState('')
  const type = types.includes(selected) ? selected : types[0]
  const media = content?.[type]
  return types.length ? <div>
    <label>미디어 타입<select value={type} onChange={event => setSelected(event.target.value)}>{types.map(item => <option key={item}>{item}</option>)}</select></label>
    {examples(document, media).map((example, index) => <div key={index}><p className="hint">{example.name}</p><pre>{json(example.value)}</pre></div>)}
    {media?.schema && <details><summary>Schema</summary><pre>{json(media.schema)}</pre></details>}
  </div> : <p className="hint">본문 없음</p>
}

function SdkJob({ projectRef, release, language, onStored }) {
  const { result, busy, start, cancel } = useRunJob(`release-sdk:${release.id}:${language}`)
  const handled = useRef('')
  useEffect(() => {
    if (result?.status === 'passed' && handled.current !== result.runId) { handled.current = result.runId; onStored() }
  }, [result?.status, result?.runId, onStored])
  const submit = async () => {
    try { await start({ language }, `/api/projects/${encodeURIComponent(projectRef)}/portal/${encodeURIComponent(release.id)}/sdk`) }
    catch { /* The shared job hook displays errors without retrying submission. */ }
  }
  return <div className="portal-sdk-job">
    <button className="primary" disabled={busy} onClick={submit}>이 릴리스로 SDK 생성</button>
    {result?.runId && ['queued', 'running'].includes(result.status) && <button className="ghost" onClick={cancel}>SDK 작업 취소</button>}
    {result && <div aria-live="polite"><p>{statuses[result.status] || '작업 확인 필요'}</p>{result.runId && <code>{result.runId}</code>}{result.error && <p role="alert">{result.error}</p>}{result.pollError && <p>{result.pollError}</p>}</div>}
  </div>
}

function ReleaseSdk({ projectRef, data, onStored }) {
  const key = `studio-release-sdk-language:${data.release.id}`
  const [language, setLanguage] = useState(() => {
    try { const saved = sessionStorage.getItem(key); return languages.some(([value]) => value === saved) ? saved : 'python' } catch { return 'python' }
  })
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const controller = useRef(null)
  useEffect(() => () => controller.current?.abort(), [])
  const artifact = data.artifacts.find(item => item.language === language)
  const download = async () => {
    const abort = new AbortController(); controller.current = abort; setBusy(true); setNotice('')
    try {
      const response = await authenticatedFetch(`/api/projects/${encodeURIComponent(projectRef)}/portal/${encodeURIComponent(data.release.id)}/sdk/${language}`, { signal: abort.signal })
      if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.error || 'SDK를 다운로드하지 못했습니다.') }
      const blob = await response.blob()
      if (abort.signal.aborted) return
      const url = URL.createObjectURL(blob); const link = document.createElement('a')
      link.href = url; link.download = artifact.filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
      setNotice(`${artifact.filename} 다운로드를 시작했습니다.`)
    } catch (error) { if (error.name !== 'AbortError') setNotice(error.message) }
    finally { if (controller.current === abort) { controller.current = null; setBusy(false) } }
  }
  return <section className="card"><h2>이 릴리스의 SDK</h2><p className="hint">현재 편집 중인 프로젝트 대신 고정된 명세 revision {data.release.projectRevision}에서 생성합니다. ZIP 안에 릴리스 정보와 원본 지문을 함께 보존합니다.</p>
    <Field label="SDK 언어"><select value={language} disabled={busy} onChange={e => { setLanguage(e.target.value); setNotice(''); try { sessionStorage.setItem(key, e.target.value) } catch { /* Optional preference. */ } }}>{languages.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
    {artifact?.purgedAt ? <p className="notice">이 SDK 파일은 관리자가 영구 정리했습니다. 다시 제공하려면 새 릴리스를 만드세요.</p> : artifact ? <div><p>원본 지문 <code>{artifact.sourceDigest}</code></p><p>ZIP SHA-256 <code>{artifact.sha256}</code></p><p>{artifact.sizeBytes.toLocaleString()} bytes · generator {artifact.generatorVersion}</p><button className="primary" disabled={busy} onClick={download}>보존된 SDK ZIP 다운로드</button></div> : data.permissions.generateSdk ? <SdkJob key={language} projectRef={projectRef} release={data.release} language={language} onStored={onStored} /> : <p className="hint">이 언어의 SDK가 아직 없습니다. 실행 권한이 있는 구성원이 생성하면 다운로드할 수 있습니다.</p>}
    {notice && <p className="notice" role="status">{notice}</p>}
  </section>
}

function PortalContent({ projectRef, releaseId, onSelectRelease }) {
  const [releases, setReleases] = useState([])
  const [cursor, setCursor] = useState(null)
  const [moreBusy, setMoreBusy] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedKey, setSelectedKey] = useState('')
  const [serverIndex, setServerIndex] = useState(0)
  const [status, setStatus] = useState('')
  const [reload, setReload] = useState(0)
  const base = `/api/projects/${encodeURIComponent(projectRef)}/portal`
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setData(null)
    const load = async () => {
      try {
        const list = await api(base, { signal: controller.signal }); setReleases(list.items); setCursor(list.nextCursor)
        if (releaseId) setData(await api(`${base}/${encodeURIComponent(releaseId)}`, { signal: controller.signal }))
      } catch (failure) { if (!controller.signal.aborted) setError(failure.message) }
      finally { if (!controller.signal.aborted) setLoading(false) }
    }
    load(); return () => controller.abort()
  }, [base, releaseId, reload])
  const items = useMemo(() => operations(data?.document || {}), [data?.document])
  const filtered = useMemo(() => searchOperations(items, search), [items, search])
  const operation = filtered.find(item => item.key === selectedKey) || filtered[0]
  const choices = servers(operation, data?.environments)
  const server = choices[serverIndex] || choices[0]
  const requestBody = resolve(data?.document || {}, operation?.requestBody)
  const responses = operation?.responses || {}
  const responseStatus = Object.hasOwn(responses, status) ? status : Object.keys(responses)[0]
  const response = resolve(data?.document || {}, responses[responseStatus])
  const more = async () => {
    if (moreBusy) return
    setMoreBusy(true)
    try { const next = await api(`${base}?before=${encodeURIComponent(cursor)}`); setReleases(current => [...current, ...next.items]); setCursor(next.nextCursor) }
    catch (failure) { setError(failure.message) }
    finally { setMoreBusy(false) }
  }
  return <>
    <section className="card"><p className="eyebrow">DEVELOPER PORTAL · WORKSPACE 전용</p><h1>릴리스 개발자 문서</h1><button className="ghost" disabled={loading} onClick={() => setReload(value => value + 1)}>문서 새로고침</button><p className="hint">발행된 명세·변경 이력·SDK를 같은 revision 기준으로 확인합니다. 이 화면에서 실제 API 요청이나 인증 흐름을 실행하지 않습니다.</p>
      <Field label="문서 릴리스"><select value={releaseId || ''} disabled={loading} onChange={e => onSelectRelease(e.target.value)}><option value="">릴리스 선택</option>{releases.map(item => <option key={item.id} value={item.id}>{item.version}{item.state === 'deprecated' ? ' · 사용 중단 예정' : ''}</option>)}{data && !releases.some(item => item.id === data.release.id) && <option value={data.release.id}>{data.release.version}</option>}</select></Field>
      {cursor && <button className="ghost" disabled={moreBusy} onClick={more}>이전 릴리스 더 보기</button>}
      {!loading && !releases.length && <p className="empty">발행된 릴리스가 없습니다.</p>}{loading && <p role="status">릴리스 문서를 불러오는 중…</p>}{error && <p role="alert">{error}</p>}
    </section>
    {data && <><section className="card portal-release-info"><h2>{data.document.info?.title} · {data.release.version}</h2>{data.release.state === 'deprecated' && <p className="notice">사용 중단 예정 릴리스입니다.</p>}<p>명세 revision {data.release.projectRevision}</p><p>원본 지문 <code>{data.release.sourceDigest}</code></p><pre>{data.document.info?.description || '명세 설명 없음'}</pre><h3>변경 내용</h3><pre>{data.release.notes || '변경 설명 없음'}</pre>{(data.release.comparison?.operationChanges || []).map(item => <p key={`${item.method}-${item.path}`}>{item.kind} · {item.method} <code>{item.path}</code></p>)}</section>
      <section className="card"><h2>API 검색</h2><Field label="API 검색어"><input value={search} onChange={e => setSearch(e.target.value)} placeholder="경로, method, 설명, tag" /></Field><p>{filtered.length} / {items.length}개 operation</p><div className="portal-operations">{filtered.map(item => <button className={operation?.key === item.key ? 'primary' : 'ghost'} key={item.key} onClick={() => { setSelectedKey(item.key); setStatus(''); setServerIndex(0) }}>{item.method} {item.path}{item.deprecated ? ' · deprecated' : ''}</button>)}</div>{!filtered.length && <p className="empty">일치하는 API가 없습니다.</p>}</section>
      {operation && <section className="card portal-operation"><h2>{operation.method} {operation.path}</h2><p>{operation.summary}</p>{operation.deprecated && <p className="notice">사용 중단 예정 operation</p>}<pre>{operation.description || ''}</pre>
        <Field label="서버·환경"><select value={Math.min(serverIndex, Math.max(choices.length - 1, 0))} onChange={e => setServerIndex(Number(e.target.value))}>{choices.length ? choices.map((item, index) => <option key={index} value={index}>{item.name} · {item.url}</option>) : <option value={0}>등록된 서버 없음</option>}</select></Field><code>{server?.url?.replace(/\/$/, '')}{operation.path}</code>
        <h3>인증 방법</h3>{operation.security?.length ? <><p className="hint">각 목록 항목은 대안이며, 한 항목 안의 여러 인증 방식은 함께 필요합니다.</p><pre>{json(operation.security)}</pre>{[...new Set(operation.security.flatMap(item => Object.keys(item)))].map(name => <div key={name}><strong>{name}</strong><pre>{json(resolve(data.document, data.document.components?.securitySchemes?.[name]) || { 안내: '명세의 security scheme 참조를 확인하세요.' })}</pre></div>)}</> : <p>명세상 인증 요구 없음</p>}
        <h3>Parameters</h3>{operation.parameters.length ? operation.parameters.map(parameter => <div key={`${parameter.in}:${parameter.name}`}><strong>{parameter.name}</strong> · {parameter.in} · {parameter.required ? '필수' : '선택'}<pre>{json(parameter)}</pre></div>) : <p className="hint">없음</p>}
        <h3>요청 예시</h3><MediaExamples key={`request-${operation.key}`} document={data.document} content={requestBody?.content} />
        <h3>응답 예시</h3><Field label="응답 상태"><select value={responseStatus || ''} onChange={e => setStatus(e.target.value)}>{Object.keys(responses).map(value => <option key={value}>{value}</option>)}</select></Field><p>{response?.description}</p><MediaExamples key={`response-${operation.key}-${responseStatus}`} document={data.document} content={response?.content} />
      </section>}
      <ReleaseSdk key={data.release.id} projectRef={projectRef} data={data} onStored={() => setReload(value => value + 1)} />
    </>}
  </>
}

export function DeveloperPortal(props) {
  return <div className="workspace"><AuthorSidebar {...props} active="portal" /><main className="editor portal-page"><PortalContent key={`${props.projectRef}:${props.releaseId || ''}`} projectRef={props.projectRef} releaseId={props.releaseId} onSelectRelease={props.onSelectRelease} /></main></div>
}
