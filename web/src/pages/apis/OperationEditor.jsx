import { useEffect, useRef, useState } from 'react'
import { Field } from '../../components/Field.jsx'
import { api } from '../../utils/studio.js'
import { HeaderFields, JsonValue, MediaFields, RawObject, SchemaFields, operationShape, parameterShape, requestBodyShape, responseShape, securityShape } from './OpenApiFields.jsx'
import { clone, editorEdit, escapePointer, namedOwner, operationOwner, pointerValue } from './openapiEditorModel.js'

const show = value => value === undefined ? '' : String(value)
const pathFor = reference => `/api/projects/${encodeURIComponent(reference)}/openapi/editor`

function OperationFields({ value, onChange, refs, file, schemes, globalSecurity, version, onValidity }) {
  const set = (key, next) => { const updated = clone(value); if (next === undefined) delete updated[key]; else updated[key] = next; onChange(updated) }
  const parameters = value.parameters || []
  const responses = value.responses || {}
  const securityMode = value.security === undefined ? 'inherit' : value.security.length ? 'explicit' : 'none'
  return <div className="oas-list">
    <section className="oas-subsection"><h3>Operation</h3><div className="oas-grid">
      {['operationId', 'summary', 'description'].map(key => <Field key={key} label={key}><input value={show(value[key])} onChange={event => set(key, event.target.value)} /></Field>)}
      <Field label="태그 (쉼표 구분)"><input value={(value.tags || []).join(', ')} onChange={event => set('tags', event.target.value.trim() ? event.target.value.split(',').map(item => item.trim()) : [])} /></Field>
      <label className="toggle"><input type="checkbox" checked={Boolean(value.deprecated)} onChange={event => set('deprecated', event.target.checked)} />deprecated</label>
    </div></section>
    <section className="oas-subsection"><h3>Parameters</h3>{parameters.map((parameter, index) => <div className="oas-entry" key={index}>
      <div className="oas-entry-heading"><strong>{parameter.name || `Parameter ${index + 1}`}</strong><button className="danger-button" onClick={() => set('parameters', parameters.filter((_, i) => i !== index))}>삭제</button></div>
      {parameter.$ref ? <p className="hint">참조 Parameter: <code>{parameter.$ref}</code></p> : <><div className="oas-grid"><Field label="이름"><input value={show(parameter.name)} onChange={event => set('parameters', parameters.map((item, i) => i === index ? { ...item, name: event.target.value } : item))} /></Field>
        <Field label="위치"><select value={parameter.in || 'query'} onChange={event => set('parameters', parameters.map((item, i) => i === index ? { ...item, in: event.target.value } : item))}>{['path', 'query', 'header', 'cookie'].map(location => <option key={location}>{location}</option>)}</select></Field>
        <Field label="설명"><input value={show(parameter.description)} onChange={event => set('parameters', parameters.map((item, i) => i === index ? { ...item, description: event.target.value } : item))} /></Field>
        <label className="toggle"><input type="checkbox" checked={Boolean(parameter.required)} disabled={parameter.in === 'path'} onChange={event => set('parameters', parameters.map((item, i) => i === index ? { ...item, required: event.target.checked } : item))} />required</label></div>
      <SchemaFields schema={parameter.schema ?? { type: 'string' }} refs={refs} ownerFile={file} version={version} onValidity={onValidity} id={`parameter.${index}.schema`} onChange={schema => set('parameters', parameters.map((item, i) => i === index ? { ...item, schema } : item))} /></>}
      <RawObject label="Parameter" value={parameter} onValidity={onValidity} id={`parameter.${index}.raw`} validate={parameterShape} onChange={next => set('parameters', parameters.map((item, i) => i === index ? next : item))} />
    </div>)}<button className="ghost" onClick={() => set('parameters', [...parameters, { name: 'newParameter', in: 'query', schema: { type: 'string' } }])}>＋ Parameter 추가</button></section>
    <section className="oas-subsection"><h3>Request body</h3>{value.requestBody ? <>
      <div className="oas-entry-heading">{!value.requestBody.$ref && <label className="toggle"><input type="checkbox" checked={Boolean(value.requestBody.required)} onChange={event => set('requestBody', { ...value.requestBody, required: event.target.checked })} />required</label>}<button className="danger-button" onClick={() => set('requestBody', undefined)}>삭제</button></div>
      {value.requestBody.$ref ? <p className="hint">참조 Request body: <code>{value.requestBody.$ref}</code></p> : <><Field label="설명"><input value={show(value.requestBody.description)} onChange={event => set('requestBody', { ...value.requestBody, description: event.target.value })} /></Field>
      <MediaFields content={value.requestBody.content || {}} refs={refs} ownerFile={file} version={version} onValidity={onValidity} id="requestBody" onChange={content => set('requestBody', { ...value.requestBody, content })} /></>}
      <RawObject label="Request body" value={value.requestBody} onValidity={onValidity} id="requestBody.raw" validate={requestBodyShape} onChange={next => set('requestBody', next)} />
    </> : <button className="ghost" onClick={() => set('requestBody', { required: false, content: { 'application/json': { schema: { type: 'object' } } } })}>＋ Request body 추가</button>}</section>
    <section className="oas-subsection"><h3>Responses</h3>{Object.entries(responses).map(([status, response]) => <div className="oas-entry" key={status}>
      <div className="oas-entry-heading"><Field label="상태 코드"><input value={status} onChange={event => { const next = event.target.value; if (!next || (next !== status && Object.hasOwn(responses, next))) return; set('responses', Object.fromEntries(Object.entries(responses).map(([key, item]) => [key === status ? next : key, item]))) }} /></Field><button className="danger-button" onClick={() => { const next = { ...responses }; delete next[status]; set('responses', next) }}>삭제</button></div>
      {response.$ref ? <p className="hint">참조 Response: <code>{response.$ref}</code></p> : <><Field label="응답 설명"><input value={show(response.description)} onChange={event => set('responses', { ...responses, [status]: { ...response, description: event.target.value } })} /></Field>
      <h4>Headers</h4><HeaderFields headers={response.headers || {}} refs={refs} ownerFile={file} version={version} onValidity={onValidity} id={`responses.${status}.headers`} onChange={headers => set('responses', { ...responses, [status]: { ...response, headers } })} />
      <h4>Media types</h4><MediaFields content={response.content || {}} refs={refs} ownerFile={file} version={version} onValidity={onValidity} id={`responses.${status}.content`} onChange={content => set('responses', { ...responses, [status]: { ...response, content } })} /></>}
      <RawObject label="Response" value={response} onValidity={onValidity} id={`responses.${status}.raw`} validate={responseShape} onChange={next => set('responses', { ...responses, [status]: next })} />
    </div>)}<button className="ghost" onClick={() => { let status = '200'; while (Object.hasOwn(responses, status)) status = status === '200' ? '400' : String(Number(status) + 1); set('responses', { ...responses, [status]: { description: 'Response', content: { 'application/json': { schema: { type: 'object' } } } } }) }}>＋ Response 추가</button></section>
    <section className="oas-subsection"><h3>Security</h3><Field label="Operation 인증 적용"><select value={securityMode} onChange={event => { if (event.target.value === 'inherit') set('security', undefined); else if (event.target.value === 'none') set('security', []); else set('security', schemes.length ? [{ [schemes[0].name]: [] }] : [{}]) }}><option value="inherit">전역 설정 상속 ({globalSecurity.length}개 요구사항)</option><option value="none">인증 없음</option><option value="explicit">Operation별 지정</option></select></Field>
      {securityMode === 'explicit' && <div className="oas-list">
        {value.security.map((requirement, index) => <div className="oas-entry-heading" key={index}>
          {Object.keys(requirement).length > 1 ? <p className="hint">AND: {Object.keys(requirement).join(' + ')} · 아래 JSON에서 편집하세요.</p> : <>
            <Field label="Scheme"><select value={Object.keys(requirement)[0] || ''} onChange={event => set('security', value.security.map((item, i) => i === index ? event.target.value ? { [event.target.value]: [] } : {} : item))}><option value="">인증 선택 사항</option>{schemes.map(item => <option key={item.name}>{item.name}</option>)}</select></Field>
            <Field label="OAuth scope (쉼표 구분)"><input disabled={!Object.keys(requirement).length} value={(Object.values(requirement)[0] || []).join(', ')} onChange={event => set('security', value.security.map((item, i) => i === index ? { ...item, [Object.keys(item)[0]]: event.target.value.trim() ? event.target.value.split(',').map(scope => scope.trim()) : [] } : item))} /></Field>
          </>}
          <button className="danger-button" onClick={() => set('security', value.security.filter((_, i) => i !== index))}>삭제</button>
        </div>)}
        <div className="actions"><button className="ghost" disabled={!schemes.length} onClick={() => set('security', [...value.security, { [schemes[0].name]: [] }])}>＋ 인증 요구사항 추가</button><button className="ghost" onClick={() => set('security', [...value.security, {}])}>＋ 인증 선택 사항</button></div>
        <p className="hint">배열의 각 객체는 OR, 한 객체 안의 여러 scheme은 AND입니다. 복합 조건은 JSON에서 편집할 수 있습니다.</p>
        <JsonValue label="Security requirements" value={value.security} onValidity={onValidity} id="operation.security" validate={securityShape} onChange={next => set('security', next)} />
      </div>}
    </section><RawObject label="Operation" value={value} onValidity={onValidity} id="operation.raw" validate={operationShape} onChange={onChange} />
  </div>
}

function SchemeFields({ value, onChange, onValidity }) {
  const set = (key, next) => { const updated = clone(value); if (!next) delete updated[key]; else updated[key] = next; onChange(updated) }
  return <div className="oas-list"><div className="oas-grid"><Field label="인증 유형"><select value={value.type || 'http'} onChange={event => onChange({ ...value, type: event.target.value })}>{['apiKey', 'http', 'oauth2', 'openIdConnect'].map(type => <option key={type}>{type}</option>)}</select></Field><Field label="설명"><input value={show(value.description)} onChange={event => set('description', event.target.value)} /></Field>
    {value.type === 'apiKey' && <><Field label="Parameter 이름"><input value={show(value.name)} onChange={event => set('name', event.target.value)} /></Field><Field label="위치"><select value={value.in || 'header'} onChange={event => set('in', event.target.value)}>{['header', 'query', 'cookie'].map(type => <option key={type}>{type}</option>)}</select></Field></>}
    {value.type === 'http' && <><Field label="Scheme"><input value={show(value.scheme)} onChange={event => set('scheme', event.target.value)} placeholder="bearer, basic" /></Field><Field label="Bearer format"><input value={show(value.bearerFormat)} onChange={event => set('bearerFormat', event.target.value)} /></Field></>}
    {value.type === 'openIdConnect' && <Field label="OpenID Connect URL"><input value={show(value.openIdConnectUrl)} onChange={event => set('openIdConnectUrl', event.target.value)} /></Field>}</div>
    {value.type === 'oauth2' && <p className="hint">OAuth 2.0 flows와 scopes는 아래 JSON에서 편집합니다.</p>}<RawObject label="Security scheme" value={value} onChange={onChange} onValidity={onValidity} id="scheme.raw" /></div>
}

function OperationEditor({ operation, projectRef, project, onSaved, onCancel }) {
  const [data, setData] = useState(null)
  const [tab, setTab] = useState(operation ? 'operation' : 'schemas')
  const [draft, setDraft] = useState(null)
  const [preview, setPreview] = useState(null)
  const [name, setName] = useState('')
  const [importSource, setImportSource] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [invalidFields, setInvalidFields] = useState({})
  const [selectionEpoch, setSelectionEpoch] = useState(0)
  const generation = useRef(0)
  const invalidate = () => { generation.current += 1; setPreview(null) }
  const validity = (id, valid) => { invalidate(); setInvalidFields(current => { const next = { ...current }; if (valid) delete next[id]; else next[id] = true; return next }) }
  useEffect(() => { let active = true; api(pathFor(projectRef)).then(result => {
    if (!active) return
    setData(result)
    if (operation) {
      const owner = operationOwner(result.catalog, operation)
      if (!owner) { setError('Operation의 원본 소유 파일을 찾을 수 없습니다.'); return }
      const original = pointerValue(result.source.files[owner.file], owner.pointer)
      setDraft({ kind: 'operation', name: `${operation.method} ${operation.path}`, owner: { ...owner, exists: true }, original, value: clone(original) })
    }
  }).catch(issue => { if (active) setError(issue.message) }); return () => { active = false; generation.current += 1 } }, [projectRef, operation?.method, operation?.path])
  const select = (kind, selected) => {
    const owner = namedOwner(data.catalog, kind === 'schema' ? 'schemas' : 'securitySchemes', selected)
    if (!owner) return
    const original = pointerValue(data.source.files[owner.file], owner.pointer)
    invalidate(); setInvalidFields({}); setSelectionEpoch(current => current + 1); setDraft({ kind, name: selected, owner: { ...owner, exists: true }, original, value: clone(original) }); setImportSource(null); setError('')
  }
  const create = kind => {
    const selected = name.trim()
    if (!/^[A-Za-z][A-Za-z0-9._-]*$/.test(selected)) { setError('이름은 영문자로 시작하고 영문자·숫자·점·밑줄·하이픈만 사용하세요.'); return }
    const group = kind === 'schema' ? 'schemas' : 'securitySchemes'
    if (namedOwner(data.catalog, group, selected)) { setError('이미 같은 이름이 있습니다.'); return }
    const value = kind === 'schema' ? { type: 'object', properties: {} } : { type: 'http', scheme: 'bearer' }
    invalidate(); setInvalidFields({}); setSelectionEpoch(current => current + 1); setDraft({ kind, name: selected, owner: { file: data.source.entrypoint, pointer: `#/components/${group}/${escapePointer(selected)}`, exists: false }, original: null, value }); setName(''); setImportSource(null); setError('')
  }
  const change = value => { invalidate(); setDraft(current => ({ ...current, value })); setError(''); setNotice('') }
  const payload = action => {
    const owner = draft?.remove && ['schema', 'scheme'].includes(draft.kind) && draft.owner.entrypointPointer ? { file: data.source.entrypoint, pointer: draft.owner.entrypointPointer, exists: true } : draft?.owner
    return { action, _storage: { revision: data._storage.revision }, sourceDigest: data.sourceDigest, ...(importSource ? { source: importSource } : { edits: [editorEdit(owner, draft.value, Boolean(draft.remove))] }) }
  }
  const submit = async action => {
    if (!data || Object.keys(invalidFields).length || (!activeDraft && !importSource) || (action === 'apply' && !preview)) return
    const currentGeneration = generation.current
    const request = action === 'apply' ? { ...preview.request, action } : payload(action)
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api(pathFor(projectRef), { method: 'POST', body: JSON.stringify(request) })
      if (generation.current !== currentGeneration) return
      if (action === 'preview') setPreview({ ...result, request })
      else { setPreview(null); await onSaved() }
    } catch (issue) { if (generation.current === currentGeneration) { setPreview(null); setError(issue.message) } }
    finally { if (generation.current === currentGeneration) setBusy(false) }
  }
  const activeDraft = draft && ((tab === 'operation' && draft.kind === 'operation') || (tab === 'schemas' && draft.kind === 'schema') || (tab === 'security' && ['scheme', 'globalSecurity'].includes(draft.kind))) ? draft : null
  const refs = (data?.catalog?.schemas || []).map(item => ({ ...item, ref: item.refByFile?.[draft?.owner?.file] || '' }))
  const schemes = data?.catalog?.securitySchemes || []
  const entrypoint = data?.source?.files?.[data.source.entrypoint] || {}
  const version = entrypoint.openapi || '3.0'
  const chooseTab = key => {
    invalidate(); setInvalidFields({}); setSelectionEpoch(current => current + 1); setTab(key)
    if (key === 'operation' && draft?.kind !== 'operation' && operation) {
      const owner = operationOwner(data.catalog, operation)
      if (owner) {
        const original = pointerValue(data.source.files[owner.file], owner.pointer)
        setDraft({ kind: 'operation', name: `${operation.method} ${operation.path}`, owner: { ...owner, exists: true }, original, value: clone(original) })
      }
    }
  }
  const sourceFile = async file => {
    if (!file) return
    invalidate(); setInvalidFields({}); setSelectionEpoch(current => current + 1)
    const currentGeneration = generation.current
    try {
      const content = await file.text()
      let source
      if (/\.ya?ml$/i.test(file.name)) source = { kind: 'bundle', entrypoint: file.name, rawFiles: { [file.name]: content } }
      else { const parsed = JSON.parse(content); source = parsed?.source?.files ? parsed.source : parsed?.files && parsed?.entrypoint ? parsed : { kind: 'file', entrypoint: file.name, files: { [file.name]: parsed } } }
      if (generation.current !== currentGeneration) return
      setImportSource(source); setDraft(null); setError('')
    } catch { if (generation.current === currentGeneration) setError('OpenAPI JSON/YAML 또는 내보낸 bundle JSON을 선택하세요.') }
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ source: data.source }, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = `${projectRef.replace(/\.json$/, '')}-openapi-bundle.json`; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
  }
  return <section className="card oas-editor" aria-label="OpenAPI 편집">
    <div className="section-header"><div><p className="eyebrow">OPENAPI EDITOR</p><h2>{operation ? `${operation.method} ${operation.path}` : 'OpenAPI 문서'} 편집</h2></div><button className="ghost" onClick={onCancel}>닫기</button></div>
    <p className="hint">원본 파일의 선택한 조각을 수정합니다. 미리보기에서 문서 전체 검증 결과를 확인한 뒤 저장합니다.</p>
    {project.docs_url && <p className="notice">저장하면 원격 문서의 프로젝트 사본이 생성됩니다.</p>}
    {error && <p role="alert" className="notice">{error}</p>}{notice && <p role="status" className="notice">{notice}</p>}
    {!data ? <p className="hint">원본 OpenAPI 문서를 불러오는 중…</p> : <fieldset className="oas-fieldset" disabled={busy}>
      <div className="oas-tabs" role="tablist" aria-label="OpenAPI 편집 영역">{[['operation', 'Operation'], ['schemas', 'Component schemas'], ['security', 'Security schemes'], ['files', '가져오기·내보내기']].filter(([key]) => key !== 'operation' || operation).map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => chooseTab(key)}>{label}</button>)}</div>
      {tab === 'operation' && draft?.kind === 'operation' && <div className="oas-list" key={selectionEpoch}>{!draft.remove && <OperationFields value={draft.value} onChange={change} refs={refs} file={draft.owner.file} schemes={schemes} globalSecurity={entrypoint.security || []} version={version} onValidity={validity} />}<button className="danger-button" onClick={() => { invalidate(); setDraft(current => ({ ...current, remove: !current.remove })) }}>{draft.remove ? '삭제 취소' : 'Operation 삭제'}</button></div>}
      {tab === 'schemas' && <div className="oas-list">
        <div className="oas-grid"><Field label="Schema 선택"><select value={draft?.kind === 'schema' ? draft.name : ''} onChange={event => select('schema', event.target.value)}><option value="">선택하세요</option>{(data.catalog.schemas || []).map(item => <option key={`${item.file}:${item.name}`} value={item.name}>{item.name} · {item.file}</option>)}</select></Field><Field label="새 schema 이름"><input value={name} onChange={event => setName(event.target.value)} /></Field></div>
        <button className="ghost" onClick={() => create('schema')}>＋ Schema 만들기</button>
        {draft?.kind === 'schema' && <div className="oas-entry" key={selectionEpoch}><div className="oas-entry-heading"><strong>{draft.name}</strong><code>{draft.owner.file}</code>{draft.owner.exists && <button className="danger-button" onClick={() => { invalidate(); setDraft(current => ({ ...current, remove: !current.remove })) }}>{draft.remove ? '삭제 취소' : 'Schema 삭제'}</button>}</div>{!draft.remove && <SchemaFields schema={draft.value} onChange={change} refs={refs} ownerFile={draft.owner.file} version={version} onValidity={validity} id={`component.${draft.name}`} />}</div>}
      </div>}
      {tab === 'security' && <div className="oas-list">
        <div className="oas-grid"><Field label="Security scheme 선택"><select value={draft?.kind === 'scheme' ? draft.name : ''} onChange={event => select('scheme', event.target.value)}><option value="">선택하세요</option>{schemes.map(item => <option key={`${item.file}:${item.name}`} value={item.name}>{item.name} · {item.file}</option>)}</select></Field><Field label="새 scheme 이름"><input value={name} onChange={event => setName(event.target.value)} /></Field></div>
        <button className="ghost" onClick={() => create('scheme')}>＋ Security scheme 만들기</button>
        {draft?.kind === 'scheme' && <div className="oas-entry" key={selectionEpoch}><div className="oas-entry-heading"><strong>{draft.name}</strong><code>{draft.owner.file}</code>{draft.owner.exists && <button className="danger-button" onClick={() => { invalidate(); setDraft(current => ({ ...current, remove: !current.remove })) }}>{draft.remove ? '삭제 취소' : 'Scheme 삭제'}</button>}</div>{!draft.remove && <SchemeFields value={draft.value} onChange={change} onValidity={validity} />}</div>}
        <div className="oas-entry" key={`global-${selectionEpoch}`}><h3>전역 Security 기본값</h3><p className="hint">Operation에서 전역 설정 상속을 선택하면 이 요구사항을 사용합니다.</p><RawObject label="전역 Security" value={{ security: draft?.kind === 'globalSecurity' ? draft.value : entrypoint.security || [] }} onValidity={validity} id="globalSecurity.raw" onChange={next => { if (!Array.isArray(next.security)) { setError('security는 배열이어야 합니다.'); return } invalidate(); setDraft({ kind: 'globalSecurity', name: '전역 Security', owner: { file: data.source.entrypoint, pointer: '#/security', exists: Object.hasOwn(entrypoint, 'security') }, original: entrypoint.security, value: next.security }); setError('') }} /></div>
      </div>}
      {tab === 'files' && <div className="oas-list"><p className="hint">OpenAPI 3.0/3.1 원본과 분할 파일을 bundle JSON으로 내보냅니다. 내보낸 파일이나 단일 JSON/YAML 명세를 다시 가져와 검증 후 적용할 수 있습니다.</p><div className="actions"><button className="ghost" onClick={download}>Bundle JSON 내보내기</button><Field label="OpenAPI 파일 가져오기"><input type="file" accept=".json,.yaml,.yml,application/json" onChange={event => sourceFile(event.target.files?.[0])} /></Field></div>{importSource && <p>가져온 명세: {Object.keys(importSource.files || importSource.rawFiles || {}).length}개 파일 · {importSource.entrypoint}</p>}</div>}
      {Object.keys(invalidFields).length > 0 && <p role="alert" className="oas-error">JSON 입력 오류를 수정해야 미리볼 수 있습니다.</p>}
      {(activeDraft || (tab === 'files' && importSource)) && <div className="oas-review-actions"><button className="ghost" disabled={busy || Object.keys(invalidFields).length > 0} onClick={() => submit('preview')}>{busy ? '검증 중…' : '변경 미리보기·전체 검증'}</button>{activeDraft?.remove && <strong>삭제 예정: {activeDraft.name}</strong>}</div>}
      {preview && <div className="oas-preview" role="region" aria-label="변경 미리보기"><h3>전체 문서 검증 {preview.valid === false ? '실패' : '완료'}</h3><p>변경 파일: {(preview.changedFiles || []).join(', ') || '없음'}</p><p>영향 가능 Operation (공유 파일 포함): {(preview.affectedOperations || []).map(item => typeof item === 'string' ? item : `${item.method} ${item.path}`).join(', ') || '없음'}</p>{(preview.issues || []).map((item, index) => <p key={index} className={item.severity === 'error' ? 'oas-error' : ''}>{item.severity} · {item.code} · {item.path} · {item.message}</p>)}<details><summary>변경 전·후 원본 확인</summary><div className="oas-diff"><div><h4>변경 전</h4><pre>{JSON.stringify(importSource ? data.source : draft.original, null, 2)}</pre></div><div><h4>변경 후</h4><pre>{JSON.stringify(importSource || (draft.remove ? null : draft.value), null, 2)}</pre></div></div></details><button className="primary" disabled={busy || preview.valid === false || !preview.changedFiles?.length || Object.keys(invalidFields).length > 0} onClick={() => submit('apply')}>{busy ? '저장 중…' : draft?.remove ? '삭제 확정' : '검증된 변경 저장'}</button></div>}
    </fieldset>}
  </section>
}

export { OperationEditor }
