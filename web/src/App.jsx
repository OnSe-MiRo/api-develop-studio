import { Component, useEffect, useState } from 'react'

const emptyCase = {
  tag: 'sample', apiName: 'api_name', fileName: 'new_case.json', method: 'GET', url: '',
  params: [{ key: '', value: '' }], authType: 'No Auth', authValue: '', headers: '', body: '',
  expectedStatus: '200', strict: true, expectedBody: '',
}

const asText = value => typeof value === 'string' ? value : ''

function jsonFileName(value) {
  const fileName = asText(value).trim()
  return fileName.endsWith('.json') ? fileName : `${fileName}.json`
}

function projectFileName(name, existingProjects) {
  const baseName = asText(name).trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'project'
  let suffix = 1
  let reference = `${baseName}.json`
  while (existingProjects.includes(reference)) {
    suffix += 1
    reference = `${baseName}-${suffix}.json`
  }
  return reference
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || '요청 처리에 실패했습니다.')
  return data
}

function parseJson(value, name, required = false) {
  const text = asText(value)
  if (!text.trim()) {
    if (required) throw new Error(`${name}을(를) 입력하세요.`)
    return undefined
  }
  try { return JSON.parse(text) } catch { throw new Error(`${name} JSON 형식이 올바르지 않습니다.`) }
}

function parseHeaders(value) {
  return asText(value).split('\n').reduce((headers, line, index) => {
    if (!line.trim()) return headers
    const separator = line.indexOf(':')
    if (separator < 1) throw new Error(`Headers ${index + 1}번째 줄은 이름: 값 형식이어야 합니다.`)
    headers[line.slice(0, separator).trim()] = line.slice(separator + 1).trim()
    return headers
  }, {})
}

function splitRequestUrl(rawUrl) {
  const value = asText(rawUrl)
  try {
    const url = new URL(value)
    return {
      baseUrl: `${url.origin}${url.pathname}${url.hash}`,
      params: [...url.searchParams.entries()].map(([key, value]) => ({ key, value })),
    }
  } catch {
    // Imported cases may contain a relative URL or a template expression. Keep it editable instead of crashing.
    const queryIndex = value.indexOf('?')
    if (queryIndex < 0) return { baseUrl: value, params: [] }
    return {
      baseUrl: value.slice(0, queryIndex),
      params: [...new URLSearchParams(value.slice(queryIndex + 1)).entries()].map(([key, value]) => ({ key, value })),
    }
  }
}

function appendParams(rawUrl, params) {
  const entries = params.filter(item => item.key)
  if (!entries.length) return rawUrl
  const query = new URLSearchParams(entries.map(item => [item.key, item.value])).toString()
  return `${rawUrl}${rawUrl.includes('?') ? '&' : '?'}${query}`
}

function Field({ label, children, wide = false }) {
  return <label className={`field ${wide ? 'wide' : ''}`}><span>{label}</span>{children}</label>
}

function JsonArea({ value, onChange, placeholder }) {
  return <textarea className="json-area" value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} spellCheck="false" />
}

function RunResult({ result }) {
  if (!result) return null
  return <section className={`run-result ${result.error || result.exitCode ? 'failure' : 'success'}`}>
    <div className="result-heading"><strong>{result.error ? '실행 오류' : result.exitCode ? `실행 실패 (종료 코드 ${result.exitCode})` : '실행 완료'}</strong></div>
    <pre>{result.error || result.output}</pre>
  </section>
}

function TestSidebar({ active, projectRef, project, onNavigate, onProjectList }) {
  const projectName = project?.name || projectRef.replace(/\.json$/, '')
  return <aside className="sidebar"><button className="sidebar-back" onClick={onProjectList}>← 프로젝트 목록</button><div className="sidebar-title">현재 프로젝트</div><div className="current-project"><strong>{projectName}</strong>{project?.base_url && <code>{project.base_url}</code>}</div><div className="sidebar-title">테스트 구성</div><div className="side-nav"><button className={active === 'cases' ? 'active' : ''} onClick={() => onNavigate('cases')}>API 케이스</button><button className={active === 'pipeline' ? 'active' : ''} onClick={() => onNavigate('pipeline')}>파이프라인</button></div></aside>
}

function CaseList({ caseItems, projectRef, project, refresh, onNavigate, onProjectList, onCreate, onOpen }) {
  const [notice, setNotice] = useState('')
  const removeCase = async reference => {
    if (!window.confirm(`${reference} 케이스를 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return
    try { await api(`/api/cases/${encodeURIComponent(reference)}`, { method: 'DELETE' }); await refresh(); setNotice(`삭제됨: case/${reference}`) } catch (error) { setNotice(error.message) }
  }
  return <div className="workspace"><TestSidebar active="cases" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">API CASES</p><h2>API 케이스 목록 <span className="count">{caseItems.length}</span></h2></div><button className="primary" onClick={onCreate}>＋ 새 케이스</button></div>{caseItems.length ? <div className="case-list">{caseItems.map(reference => { const [tag, apiName, fileName] = reference.split('/'); return <article className="case-list-item" key={reference}><button className="case-list-row" onClick={() => onOpen(reference)}><span className="case-list-icon">{tag?.slice(0, 1).toUpperCase() || 'A'}</span><span><strong>{apiName || reference}</strong><small>{tag} · {fileName}</small></span><span className="case-list-action">수정 · 실행 <b>→</b></span></button><button className="case-list-delete" aria-label={`${reference} 케이스 삭제`} title="케이스 삭제" onClick={() => removeCase(reference)}>×</button></article> })}</div> : <div className="empty">저장된 API 케이스가 없습니다. 새 케이스를 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main></div>
}

function CaseEditor({ refresh, projectRef, project, caseReference, onNavigate, onProjectList, onBack }) {
  const [form, setForm] = useState(emptyCase)
  const [requestTab, setRequestTab] = useState('Params')
  const [selected, setSelected] = useState('')
  const [notice, setNotice] = useState('')
  const [result, setResult] = useState(null)
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }))
  const caseRef = `${asText(form.tag)}/${asText(form.apiName)}/${jsonFileName(form.fileName)}`
  useEffect(() => {
    setResult(null)
    if (caseReference) load(caseReference)
    else { setForm(emptyCase); setSelected(''); setNotice('새 API 케이스를 작성하세요.') }
  }, [caseReference, projectRef])

  const updateParam = (index, key, value) => setForm(current => {
    const params = current.params.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item)
    if (index === params.length - 1 && (params[index].key || params[index].value)) params.push({ key: '', value: '' })
    return { ...current, params }
  })
  const removeParam = index => setForm(current => ({ ...current, params: current.params.length === 1 ? [{ key: '', value: '' }] : current.params.filter((_, itemIndex) => itemIndex !== index) }))

  const load = async reference => {
    if (!reference) return
    try {
      const data = await api(`/api/cases/${encodeURIComponent(reference)}`)
      // Cases created before path normalization on Windows may still use backslashes.
      const [tag, apiName, fileName] = asText(reference).split(/[\\/]/)
      const request = data.request || {}, expected = data.expected || {}
      const requestUrl = splitRequestUrl(request.url)
      const headers = { ...(request.headers || {}) }
      const authorization = asText(headers.Authorization)
      delete headers.Authorization
      setForm({
        tag: asText(tag), apiName: asText(apiName), fileName: asText(fileName), method: asText(request.method) || 'GET', url: requestUrl.baseUrl,
        params: requestUrl.params.concat({ key: '', value: '' }),
        authType: authorization.startsWith('Bearer ') ? 'Bearer Token' : 'No Auth', authValue: authorization.replace(/^Bearer /, ''),
        headers: Object.entries(headers).map(([key, value]) => `${key}: ${value}`).join('\n'),
        body: request.body === undefined ? '' : JSON.stringify(request.body, null, 2), expectedStatus: String(expected.status ?? 200),
        strict: expected.strict ?? true, expectedBody: data._expectedBodyRaw ?? (expected.body === undefined ? '' : JSON.stringify(expected.body, null, 2)),
      })
      setSelected(reference); setNotice(`불러옴: ${reference}`); setResult(null)
    } catch (error) { setNotice(error.message) }
  }

  const document = () => {
    if (!projectRef) throw new Error('프로젝트를 먼저 선택하세요.')
    if (!form.tag || !form.apiName || !form.fileName || !form.url) throw new Error('Tag, API 이름, 케이스 파일, URL을 입력하세요.')
    const headers = parseHeaders(form.headers)
    if (form.authType === 'Bearer Token') {
      if (!form.authValue) throw new Error('Bearer Token을 입력하세요.')
      headers.Authorization = `Bearer ${form.authValue}`
    }
    const request = { method: form.method, url: appendParams(form.url, form.params) }
    const body = parseJson(form.body, 'Request body')
    if (Object.keys(headers).length) request.headers = headers
    if (body !== undefined) request.body = body
    const expected = { status: Number(form.expectedStatus), strict: form.strict }
    if (!Number.isInteger(expected.status)) throw new Error('Expected status는 정수여야 합니다.')
    const expectedBody = parseJson(form.expectedBody, 'Expected body')
    if (expectedBody !== undefined) expected.body = expectedBody
    return { project: projectRef, request, expected }
  }

  const casePayload = () => ({ ...document(), _expectedBodyRaw: form.expectedBody })

  const save = async () => {
    try {
      await api(`/api/cases/${encodeURIComponent(caseRef)}`, { method: 'PUT', body: JSON.stringify(casePayload()) })
      await refresh(); setSelected(caseRef); setNotice(`저장됨: case/${caseRef}`); return true
    } catch (error) { setNotice(error.message); return false }
  }
  const runOnly = async () => {
    try {
      setResult(null); setNotice('현재 입력값을 저장하지 않고 실행 중입니다.')
      setResult(await api('/api/run', { method: 'POST', body: JSON.stringify({ inlineCase: casePayload(), caseReference: caseRef }) }))
      setNotice('저장하지 않고 실행했습니다.')
    } catch (error) { setResult({ error: error.message }); setNotice(error.message) }
  }
  const run = async () => {
    if (!(await save())) return
    try { setResult(await api('/api/run', { method: 'POST', body: JSON.stringify({ cases: [caseRef] }) })) }
    catch (error) { setResult({ error: error.message }) }
  }
  const removeCase = async () => {
    if (!selected) return setNotice('삭제할 저장된 케이스를 먼저 선택하세요.')
    if (!window.confirm(`${selected} 케이스를 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return
    try {
      await api(`/api/cases/${encodeURIComponent(selected)}`, { method: 'DELETE' })
      await refresh(); setForm(emptyCase); setSelected(''); setResult(null); setNotice(`삭제됨: case/${selected}`)
    } catch (error) { setNotice(error.message) }
  }

  return <div className="workspace">
    <TestSidebar active="cases" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} />
    <main className="editor">
      <section className="card"><div className="section-header"><div><p className="eyebrow">CASE SETTINGS</p><h2>{selected ? 'API 케이스 설정' : '새 API 케이스'}</h2></div><div className="actions"><button className="ghost" onClick={onBack}>목록으로</button>{selected && <button className="danger-button" onClick={removeCase}>삭제</button>}<button className="ghost" onClick={save}>저장</button><button className="ghost" onClick={runOnly}>실행만</button><button className="primary" onClick={run}>저장 후 실행</button></div></div>
        <div className="form-grid three"><Field label="Tag"><input value={form.tag} onChange={event => set('tag', event.target.value)} /></Field><Field label="API 이름"><input value={form.apiName} onChange={event => set('apiName', event.target.value)} /></Field><Field label="케이스 파일"><input value={form.fileName} onChange={event => set('fileName', event.target.value)} /></Field></div>
      </section>
      <section className="card request-card"><div className="request-bar"><select className="method" value={form.method} onChange={event => set('method', event.target.value)}>{['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(method => <option key={method}>{method}</option>)}</select><input className="url-input" value={form.url} placeholder="/v1/users (프로젝트 Base URL 기준)" onChange={event => set('url', event.target.value)} /></div>
        <div className="tabs">{['Params', 'Authorization', 'Headers', 'Body'].map(tab => <button key={tab} className={requestTab === tab ? 'active' : ''} onClick={() => setRequestTab(tab)}>{tab}</button>)}</div>
        <div className="tab-content">{requestTab === 'Params' && <><div className="param-header"><span>Key</span><span>Value</span><span /></div>{form.params.map((param, index) => <div className="param-row" key={index}><input value={param.key} placeholder="page" onChange={event => updateParam(index, 'key', event.target.value)} /><input value={param.value} placeholder="1" onChange={event => updateParam(index, 'value', event.target.value)} /><button className="icon" onClick={() => removeParam(index)}>×</button></div>)}<button className="text-button" onClick={() => setForm(current => ({ ...current, params: [...current.params, { key: '', value: '' }] }))}>＋ Parameter 추가</button></>}
          {requestTab === 'Authorization' && <div className="auth-form"><Field label="Type"><select value={form.authType} onChange={event => set('authType', event.target.value)}><option>No Auth</option><option>Bearer Token</option></select></Field>{form.authType === 'Bearer Token' && <Field label="Token" wide><input type="password" value={form.authValue} onChange={event => set('authValue', event.target.value)} placeholder="토큰 값" /></Field>}</div>}
          {requestTab === 'Headers' && <JsonArea value={form.headers} onChange={value => set('headers', value)} placeholder={'Content-Type: application/json\nX-Request-Id: example'} />}
          {requestTab === 'Body' && <JsonArea value={form.body} onChange={value => set('body', value)} placeholder={'{\n  "name": "Ada"\n}'} />}
        </div>
      </section>
      <section className="card"><div className="section-header"><div><p className="eyebrow">ASSERTION</p><h2>기대 응답</h2></div></div><div className="expected-controls"><Field label="Expected status"><input value={form.expectedStatus} onChange={event => set('expectedStatus', event.target.value)} /></Field><label className="toggle"><input type="checkbox" checked={form.strict} onChange={event => set('strict', event.target.checked)} /><span>strict 비교</span></label></div><JsonArea value={form.expectedBody} onChange={value => set('expectedBody', value)} placeholder={'{\n  "id": 1\n}'} /></section>
      {notice && <p className="notice">{notice}</p>}<RunResult result={result} />
    </main>
  </div>
}

function PipelineList({ pipelineItems, projectRef, project, refresh, onNavigate, onProjectList, onCreate, onOpen }) {
  const [notice, setNotice] = useState('')
  const removePipeline = async reference => {
    if (!window.confirm(`${reference} 파이프라인을 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return
    try { await api(`/api/pipelines/${encodeURIComponent(reference)}`, { method: 'DELETE' }); await refresh(); setNotice(`삭제됨: pipelines/${reference}`) } catch (error) { setNotice(error.message) }
  }
  return <div className="workspace"><TestSidebar active="pipeline" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">PIPELINES</p><h2>파이프라인 목록 <span className="count">{pipelineItems.length}</span></h2></div><button className="primary" onClick={onCreate}>＋ 새 파이프라인</button></div>{pipelineItems.length ? <div className="case-list">{pipelineItems.map(reference => <article className="case-list-item" key={reference}><button className="case-list-row" onClick={() => onOpen(reference)}><span className="case-list-icon">P</span><span><strong>{reference.replace(/\.json$/, '')}</strong><small>{reference}</small></span><span className="case-list-action">수정 · 실행 <b>→</b></span></button><button className="case-list-delete" aria-label={`${reference} 파이프라인 삭제`} title="파이프라인 삭제" onClick={() => removePipeline(reference)}>×</button></article>)}</div> : <div className="empty">저장된 파이프라인이 없습니다. 새 파이프라인을 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main></div>
}

function PipelineEditor({ caseItems, refresh, projectRef, project, onNavigate, onProjectList, pipelineReference, onBack }) {
  const [fileName, setFileName] = useState('new_pipeline.json')
  const [defaults, setDefaults] = useState({ retry: 0, retry_interval_seconds: 0 })
  const [steps, setSteps] = useState([])
  const [draft, setDraft] = useState({ name: '', case: '', retry: '', interval: '', continue: false })
  const [selected, setSelected] = useState('')
  const [notice, setNotice] = useState('')
  const [result, setResult] = useState(null)
  const ref = jsonFileName(fileName)
  useEffect(() => { if (!draft.case && caseItems.length) setDraft(current => ({ ...current, case: caseItems[0] })) }, [caseItems])
  useEffect(() => {
    setResult(null)
    if (pipelineReference) load(pipelineReference)
    else { setFileName('new_pipeline.json'); setDefaults({ retry: 0, retry_interval_seconds: 0 }); setSteps([]); setDraft({ name: '', case: '', retry: '', interval: '', continue: false }); setSelected(''); setNotice('새 파이프라인을 작성하세요.') }
  }, [pipelineReference, projectRef])
  const load = async reference => {
    if (!reference) return
    try { const data = await api(`/api/pipelines/${encodeURIComponent(reference)}`); setFileName(reference); setDefaults(data.defaults || { retry: 0, retry_interval_seconds: 0 }); setSteps(data.steps || []); setSelected(reference); setNotice(`불러옴: ${reference}`); setResult(null) } catch (error) { setNotice(error.message) }
  }
  const addStep = () => {
    if (!draft.name || !draft.case) return setNotice('단계 이름과 케이스를 선택하세요.')
    if (steps.some(step => step.name === draft.name)) return setNotice('단계 이름은 고유해야 합니다.')
    const step = { name: draft.name, case: draft.case }
    if (draft.retry !== '') step.retry = Number(draft.retry)
    if (draft.interval !== '') step.retry_interval_seconds = Number(draft.interval)
    if (draft.continue) step.continue_on_failure = true
    setSteps(current => [...current, step]); setDraft(current => ({ ...current, name: '', retry: '', interval: '', continue: false }))
  }
  const pipelineDocument = () => {
    if (!projectRef) throw new Error('프로젝트를 먼저 선택하세요.')
    if (!steps.length) throw new Error('최소 한 개의 단계를 추가하세요.')
    return { project: projectRef, defaults: { retry: Number(defaults.retry), retry_interval_seconds: Number(defaults.retry_interval_seconds) }, steps }
  }
  const save = async () => {
    try { await api(`/api/pipelines/${encodeURIComponent(ref)}`, { method: 'PUT', body: JSON.stringify(pipelineDocument()) }); await refresh(); setSelected(ref); setNotice(`저장됨: pipelines/${ref}`); return true } catch (error) { setNotice(error.message); return false }
  }
  const runOnly = async () => {
    try {
      setResult(null); setNotice('현재 파이프라인을 저장하지 않고 실행 중입니다.')
      setResult(await api('/api/run', { method: 'POST', body: JSON.stringify({ inlinePipeline: pipelineDocument() }) }))
      setNotice('저장하지 않고 실행했습니다.')
    } catch (error) { setResult({ error: error.message }); setNotice(error.message) }
  }
  const run = async () => { if (!(await save())) return; try { setResult(await api('/api/run', { method: 'POST', body: JSON.stringify({ pipelines: [ref] }) })) } catch (error) { setResult({ error: error.message }) } }
  const removePipeline = async () => {
    if (!selected) return setNotice('삭제할 저장된 파이프라인을 먼저 선택하세요.')
    if (!window.confirm(`${selected} 파이프라인을 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return
    try {
      await api(`/api/pipelines/${encodeURIComponent(selected)}`, { method: 'DELETE' })
      await refresh(); setFileName('new_pipeline.json'); setSteps([]); setSelected(''); setResult(null); setNotice(`삭제됨: pipelines/${selected}`)
    } catch (error) { setNotice(error.message) }
  }
  const move = (index, offset) => setSteps(current => { const target = index + offset; if (target < 0 || target >= current.length) return current; const next = [...current]; [next[index], next[target]] = [next[target], next[index]]; return next })
  return <div className="workspace"><TestSidebar active="pipeline" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">PIPELINE SETTINGS</p><h2>{selected ? '파이프라인 설정' : '새 파이프라인'}</h2></div><div className="actions"><button className="ghost" onClick={onBack}>목록으로</button>{selected && <button className="danger-button" onClick={removePipeline}>삭제</button>}<button className="ghost" onClick={save}>저장</button><button className="ghost" onClick={runOnly}>실행만</button><button className="primary" onClick={run}>저장 후 실행</button></div></div><div className="form-grid three"><Field label="파일명"><input value={fileName} onChange={event => setFileName(event.target.value)} /></Field><Field label="기본 재시도"><input type="number" min="0" value={defaults.retry} onChange={event => setDefaults(current => ({ ...current, retry: event.target.value }))} /></Field><Field label="기본 간격 (초)"><input type="number" min="0" step="0.1" value={defaults.retry_interval_seconds} onChange={event => setDefaults(current => ({ ...current, retry_interval_seconds: event.target.value }))} /></Field></div></section><section className="card"><div className="section-header"><div><p className="eyebrow">ADD STEP</p><h2>테스트 단계 추가</h2></div></div><div className="form-grid step-grid"><Field label="케이스" wide><select value={draft.case} onChange={event => setDraft(current => ({ ...current, case: event.target.value }))} disabled={!projectRef}>{caseItems.map(item => <option key={item}>{item}</option>)}</select></Field><Field label="단계 이름"><input value={draft.name} onChange={event => setDraft(current => ({ ...current, name: event.target.value }))} placeholder="get_user" /></Field><Field label="재시도 (선택)"><input type="number" min="0" value={draft.retry} onChange={event => setDraft(current => ({ ...current, retry: event.target.value }))} /></Field><Field label="간격 (선택)"><input type="number" min="0" step="0.1" value={draft.interval} onChange={event => setDraft(current => ({ ...current, interval: event.target.value }))} /></Field></div><div className="step-actions"><label className="toggle"><input type="checkbox" checked={draft.continue} onChange={event => setDraft(current => ({ ...current, continue: event.target.checked }))} /><span>실패해도 다음 단계 실행</span></label><button className="primary" onClick={addStep}>＋ 단계 추가</button></div></section><section className="card"><div className="section-header"><div><p className="eyebrow">EXECUTION ORDER</p><h2>실행 순서 <span className="count">{steps.length}</span></h2></div></div><div className="steps">{steps.length ? steps.map((step, index) => <div className="step" key={step.name}><span className="order">{String(index + 1).padStart(2, '0')}</span><div><strong>{step.name}</strong><small>{step.case}</small></div><div className="step-meta">재시도 {step.retry ?? '기본값'} · 간격 {step.retry_interval_seconds ?? '기본값'}</div><div className="row-actions"><button className="icon" onClick={() => move(index, -1)}>↑</button><button className="icon" onClick={() => move(index, 1)}>↓</button><button className="icon danger" onClick={() => setSteps(current => current.filter((_, itemIndex) => itemIndex !== index))}>×</button></div></div>) : <div className="empty">API 케이스를 먼저 저장한 뒤 단계로 추가하세요.</div>}</div></section>{notice && <p className="notice">{notice}</p>}<RunResult result={result} /></main></div>
}

function ProjectList({ projects, activeProject, onOpenProject, onCreateProject, refresh }) {
  const [notice, setNotice] = useState('')
  const removeProject = async reference => {
    if (!window.confirm(`${reference.replace(/\.json$/, '')} 프로젝트를 삭제할까요?\n연결된 API 케이스나 파이프라인이 있으면 삭제할 수 없습니다.`)) return
    try {
      await api(`/api/projects/${encodeURIComponent(reference)}`, { method: 'DELETE' })
      await refresh('')
      setNotice(`삭제됨: projects/${reference}`)
    } catch (error) { setNotice(error.message) }
  }
  return <main className="project-page"><section className="card project-list-card"><div className="section-header"><div><p className="eyebrow">SELECT PROJECT</p><h2>프로젝트 목록</h2></div><button className="primary" onClick={onCreateProject}>＋ 새 프로젝트 만들기</button></div>{projects.length ? <div className="project-grid">{projects.map(reference => <article className={`project-card ${activeProject === reference ? 'active' : ''}`} key={reference}><button className="project-card-open" onClick={() => onOpenProject(reference)}><span className="project-card-label">PROJECT</span><strong>{reference.replace(/\.json$/, '')}</strong><small>{reference}</small><span className="project-card-action">API 테스트 열기 <b>→</b></span></button><button className="project-card-delete" aria-label={`${reference} 프로젝트 삭제`} title="프로젝트 삭제" onClick={() => removeProject(reference)}>×</button></article>)}</div> : <div className="empty">등록된 프로젝트가 없습니다. 새 프로젝트를 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main>
}

function ProjectSettings({ projects, onSaved, onCancel }) {
  const [form, setForm] = useState({ name: '', baseUrl: '', proxy: '', verify: true })
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }))
  const save = async () => {
    try {
      if (!form.name || !form.baseUrl) throw new Error('프로젝트 이름과 Base URL을 입력하세요.')
      const reference = projectFileName(form.name, projects)
      await api(`/api/projects/${encodeURIComponent(reference)}`, { method: 'PUT', body: JSON.stringify({ name: form.name, base_url: form.baseUrl, advanced: { proxy: form.proxy, verify: form.verify } }) })
      await onSaved(reference)
    } catch (error) { setNotice(error.message) }
  }
  return <main className="project-page"><section className="card"><div className="section-header"><div><p className="eyebrow">NEW PROJECT</p><h2>프로젝트 설정</h2></div><div className="actions"><button className="ghost" onClick={onCancel}>목록으로</button><button className="primary" onClick={save}>저장</button></div></div><div className="form-grid project-settings-grid"><Field label="프로젝트 이름"><input value={form.name} onChange={event => set('name', event.target.value)} placeholder="New Project" /></Field><Field label="Base URL"><input value={form.baseUrl} onChange={event => set('baseUrl', event.target.value)} placeholder="https://api.example.com" /></Field></div><section className="advanced-settings"><button className="advanced-toggle" onClick={() => setAdvancedOpen(current => !current)}><span>고급 설정</span><span>{advancedOpen ? '−' : '+'}</span></button>{advancedOpen && <div className="advanced-content"><Field label="Proxy URL"><input value={form.proxy} onChange={event => set('proxy', event.target.value)} placeholder="http://proxy.example.com:8080" /></Field><label className="toggle"><input type="checkbox" checked={form.verify} onChange={event => set('verify', event.target.checked)} /><span>TLS 인증서 검증 (verify)</span></label><p className="hint">프록시를 비우면 직접 연결합니다. verify를 끄면 자체 서명 인증서 등의 TLS 검증을 생략합니다.</p></div>}</section><p className="hint">프로젝트 JSON 파일은 프로젝트 이름을 기준으로 자동 생성됩니다. 케이스의 URL에 <code>/users</code>처럼 상대 경로를 입력하면 이 Base URL과 결합해 실행합니다. 절대 URL도 그대로 실행할 수 있습니다.</p></section>{notice && <p className="notice">{notice}</p>}</main>
}

function StudioApp() {
  const [tab, setTab] = useState('project')
  const [projects, setProjects] = useState([])
  const [activeProject, setActiveProject] = useState('')
  const [project, setProject] = useState(null)
  const [caseItems, setCaseItems] = useState([])
  const [pipelineItems, setPipelineItems] = useState([])
  const [caseReference, setCaseReference] = useState('')
  const [pipelineReference, setPipelineReference] = useState('')
  const [error, setError] = useState('')
  const refresh = async (preferredProject = activeProject) => {
    try {
      const projectData = await api('/api/projects')
      const selectedProject = projectData.items.includes(preferredProject) ? preferredProject : (projectData.items[0] || '')
      const filter = selectedProject ? `?project=${encodeURIComponent(selectedProject)}` : '?project=__none__'
      const [cases, pipelines, selectedDocument] = await Promise.all([
        api(`/api/cases${filter}`), api(`/api/pipelines${filter}`), selectedProject ? api(`/api/projects/${encodeURIComponent(selectedProject)}`) : Promise.resolve(null),
      ])
      setProjects(projectData.items); setActiveProject(selectedProject); setProject(selectedDocument); setCaseItems(cases.items); setPipelineItems(pipelines.items); setError('')
    } catch (requestError) { setError(`서버 연결 오류: ${requestError.message}`) }
  }
  const selectProject = async reference => { setCaseReference(''); setPipelineReference(''); await refresh(reference) }
  const openProject = async reference => { await selectProject(reference); setTab('case-list') }
  const saveProjectAndOpen = async reference => { await openProject(reference) }
  const navigateTest = target => {
    if (target === 'cases') { setCaseReference(''); setTab('case-list') }
    else { setPipelineReference(''); setTab('pipeline-list') }
  }
  const openCase = reference => { setCaseReference(reference); setTab('case-settings') }
  const createCase = () => { setCaseReference(''); setTab('case-settings') }
  const openPipeline = reference => { setPipelineReference(reference); setTab('pipeline-settings') }
  const createPipeline = () => { setPipelineReference(''); setTab('pipeline-settings') }
  useEffect(() => { refresh() }, [])
  const editorProps = { caseItems, pipelineItems, projects, projectRef: activeProject, project, onProjectChange: selectProject, refresh, onNavigate: navigateTest, onProjectList: () => setTab('project') }
  return <><header className="topbar"><div className="brand"><span>⚡</span><div><strong>API Test Studio</strong><small>프로젝트별 JSON API 테스트</small></div></div><nav><button className={tab === 'project' || tab === 'project-settings' ? 'selected' : ''} onClick={() => setTab('project')}>프로젝트 목록</button></nav><button className="ghost refresh" onClick={() => refresh()}>↻ 새로고침</button></header>{error && <div className="connection-error">{error} — Python 서버를 먼저 실행하세요: <code>python3 react_server.py</code></div>}{tab === 'project' ? <ProjectList projects={projects} activeProject={activeProject} onOpenProject={openProject} onCreateProject={() => setTab('project-settings')} refresh={refresh} /> : tab === 'project-settings' ? <ProjectSettings projects={projects} onSaved={saveProjectAndOpen} onCancel={() => setTab('project')} /> : tab === 'case-list' ? <CaseList {...editorProps} onCreate={createCase} onOpen={openCase} /> : tab === 'case-settings' ? <CaseEditor {...editorProps} caseReference={caseReference} onBack={() => navigateTest('cases')} /> : tab === 'pipeline-list' ? <PipelineList {...editorProps} onCreate={createPipeline} onOpen={openPipeline} /> : <PipelineEditor {...editorProps} pipelineReference={pipelineReference} onBack={() => navigateTest('pipeline')} />}</>
}

class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return <main className="fatal-error"><p className="eyebrow">UNEXPECTED ERROR</p><h1>화면을 표시할 수 없습니다.</h1><p>{this.state.error.message}</p><button className="primary" onClick={() => window.location.reload()}>새로고침</button></main>
    return this.props.children
  }
}

export default function App() {
  return <ErrorBoundary><StudioApp /></ErrorBoundary>
}
