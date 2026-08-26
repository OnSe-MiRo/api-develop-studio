import { Component, useEffect, useState } from 'react'

const emptyCase = {
  tag: 'sample', apiName: 'api_name', fileName: 'new_case', method: 'GET', url: '',
  params: [{ key: '', value: '' }], authType: 'No Auth', authValue: '', headers: '', body: '', bodyMode: 'json', formData: [],
  expectedStatus: '200', strict: true, expectedBody: '', validateExact: true, validateConditions: false, assertions: [], secretVariables: [],
}

const asText = value => typeof value === 'string' ? value : ''
const docValue = value => value === undefined || value === null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
const emptyFormDataRow = () => ({ key: '', kind: 'text', value: '', file: null, storedFile: '', filename: '', contentType: '' })
const jsonType = value => value === null ? 'null' : Array.isArray(value) ? 'array' : Number.isInteger(value) ? 'integer' : typeof value === 'number' ? 'number' : typeof value === 'string' ? 'string' : typeof value === 'boolean' ? 'boolean' : 'object'
const typeLabel = type => ({ number: '숫자', integer: '정수', string: '문자열', boolean: 'boolean', object: '객체', array: '배열', null: 'null' }[type] || type)
const defaultAssertionOperator = type => type === 'string' || type === 'array' ? 'length_between' : ['boolean', 'object', 'null'].includes(type) ? 'type' : 'between'
const emptyAssertionRow = variable => {
  const operator = defaultAssertionOperator(variable?.type)
  return { path: variable?.path || 'body.', operator, value: operator === 'type' ? variable?.type || 'number' : '', min: '', max: '', includeMin: true, includeMax: true, confirmed: false }
}
const assertionOperators = [
  ['between', '범위 내'], ['gte', '이상'], ['gt', '초과'], ['lte', '이하'], ['lt', '미만'],
  ['exists', '필드 존재'], ['not_exists', '필드 미존재'], ['type', '데이터 타입'], ['length_between', '길이 범위'],
]
const assertionTypes = [['number', '숫자'], ['integer', '정수'], ['string', '문자열'], ['boolean', 'boolean'], ['object', '객체'], ['array', '배열'], ['null', 'null']]
const assertionFormRow = assertion => ({
  path: asText(assertion?.path), operator: asText(assertion?.operator) || 'between',
  value: assertion?.value === undefined ? '' : String(assertion.value),
  min: assertion?.min === undefined ? '' : String(assertion.min), max: assertion?.max === undefined ? '' : String(assertion.max),
  includeMin: assertion?.include_min ?? true, includeMax: assertion?.include_max ?? true, confirmed: true,
})
const assertionCanConfirm = assertion => {
  if (!asText(assertion.path).trim()) return false
  if (assertion.operator === 'between' || assertion.operator === 'length_between') {
    if (asText(assertion.min).trim() === '' || asText(assertion.max).trim() === '') return false
    const min = Number(assertion.min), max = Number(assertion.max)
    if (!Number.isFinite(min) || !Number.isFinite(max) || min > max) return false
    return assertion.operator !== 'length_between' || (Number.isInteger(min) && Number.isInteger(max) && min >= 0)
  }
  if (['gt', 'gte', 'lt', 'lte'].includes(assertion.operator)) return asText(assertion.value).trim() !== '' && Number.isFinite(Number(assertion.value))
  if (assertion.operator === 'type') return assertionTypes.some(([value]) => value === assertion.value)
  return true
}
const assertionSummary = assertion => {
  const path = asText(assertion.path).trim() || '응답 경로 미지정'
  if (assertion.operator === 'between') return `${path} · ${assertion.min} ${assertion.includeMin ? '이상' : '초과'} · ${assertion.max} ${assertion.includeMax ? '이하' : '미만'}`
  if (assertion.operator === 'length_between') return `${path} · 길이 ${assertion.min}~${assertion.max}`
  if (assertion.operator === 'type') return `${path} · 타입 ${typeLabel(assertion.value)}`
  if (assertion.operator === 'exists') return `${path} · 필드 존재`
  if (assertion.operator === 'not_exists') return `${path} · 필드 미존재`
  const operatorLabel = Object.fromEntries(assertionOperators)[assertion.operator] || assertion.operator
  return `${path} · ${assertion.value} ${operatorLabel}`
}
const newCaseForm = () => ({ ...emptyCase, params: [{ key: '', value: '' }], formData: [], assertions: [] })

function responseVariablesFromJson(rawValue) {
  let body
  try { body = JSON.parse(asText(rawValue)) } catch { return [] }
  const variables = []
  const visit = (value, path) => {
    const type = jsonType(value)
    const example = type === 'object' ? `{${Object.keys(value).length}개 키}` : type === 'array' ? `[${value.length}개 항목]` : JSON.stringify(value)
    variables.push({ path, type, example })
    if (type === 'object') Object.entries(value).filter(([key]) => /^[A-Za-z_][\w-]*$/.test(key)).forEach(([key, item]) => visit(item, `${path}.${key}`))
    if (type === 'array') value.forEach((item, index) => visit(item, `${path}.${index}`))
  }
  if (jsonType(body) === 'object') {
    Object.entries(body).filter(([key]) => /^[A-Za-z_][\w-]*$/.test(key)).forEach(([key, item]) => visit(item, `body.${key}`))
  } else {
    visit(body, 'body')
  }
  return variables
}

function jsonFileName(value) {
  const fileName = asText(value).trim()
  return fileName.endsWith('.json') ? fileName : `${fileName}.json`
}

function caseName(value) {
  return asText(value).replace(/\.json$/i, '')
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

async function uploadAttachment(reference, file) {
  const response = await fetch(`/api/uploads/${encodeURIComponent(reference)}`, {
    method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || '파일 업로드에 실패했습니다.')
  return data.path
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

function caseSignature(reference, payload) {
  const expected = payload?.expected || {}
  const expectedBodyRaw = typeof payload?._expectedBodyRaw === 'string'
    ? payload._expectedBodyRaw
    : expected.body === undefined ? '' : JSON.stringify(expected.body, null, 2)
  return JSON.stringify({ reference, project: payload?.project, request: payload?.request, expected, expectedBodyRaw })
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

function AssertionEditor({ assertions, variables, enabled, onAdd, onUpdate, onConfirm, onSelectVariable, onRemove }) {
  return <div className={`assertion-builder ${enabled ? '' : 'inactive'}`}>
    <div className="assertion-heading"><div><div className="assertion-title"><strong>변수별 조건 설정</strong><span className={`method-status ${enabled ? 'enabled' : ''}`}>{enabled ? '실행 대상' : '실행 제외'}</span></div><p className="hint">{variables.length ? `기대 응답에서 ${variables.length}개 변수를 찾았습니다. ` : '기대 응답 JSON을 입력하면 변수를 자동으로 찾습니다. '}각 변수에 독립적인 조건을 등록할 수 있습니다.{enabled ? ' 등록한 모든 조건을 만족해야 통과합니다.' : ' 설정은 보존되지만 현재 실행에서는 검사하지 않습니다.'}</p></div><button className="ghost" onClick={onAdd}>＋ 변수 조건 추가</button></div>
    {assertions.length ? <div className="assertion-list">{assertions.map((assertion, index) => {
      const rangeOperator = assertion.operator === 'between' || assertion.operator === 'length_between'
      const valueOperator = ['gt', 'gte', 'lt', 'lte'].includes(assertion.operator)
      const selectedVariable = variables.find(variable => variable.path === assertion.path)
      if (assertion.confirmed) return <div className="assertion-summary-row" key={index}>
        <div className="assertion-summary"><span className="assertion-check">✓</span><span><small>응답 변수 {index + 1}</small><strong>{assertionSummary(assertion)}</strong></span></div>
        <div className="assertion-summary-actions"><button className="ghost" onClick={() => onUpdate(index, 'confirmed', false)}>수정</button><button className="icon danger" aria-label={`${index + 1}번째 조건 삭제`} title="조건 삭제" onClick={() => onRemove(index)}>×</button></div>
      </div>
      return <div className="assertion-row" key={index}>
        <div className="assertion-target"><Field label={`응답 변수 ${index + 1}`}><select value={selectedVariable?.path || '__custom__'} onChange={event => { const variable = variables.find(item => item.path === event.target.value); onSelectVariable(index, variable) }}><option value="__custom__">직접 경로 입력</option>{variables.map(variable => <option key={variable.path} value={variable.path}>{variable.path} · {typeLabel(variable.type)} · {variable.example}</option>)}</select></Field>{selectedVariable ? <small>{typeLabel(selectedVariable.type)} 변수 · 예시 {selectedVariable.example}</small> : <Field label="직접 경로"><input value={assertion.path} placeholder="body.age 또는 body.items.0" onChange={event => onUpdate(index, 'path', event.target.value)} /></Field>}</div>
        <Field label="조건"><select value={assertion.operator} onChange={event => onUpdate(index, 'operator', event.target.value)}>{assertionOperators.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        {rangeOperator ? <div className="assertion-range"><Field label="최솟값"><input type="number" min={assertion.operator === 'length_between' ? '0' : undefined} step={assertion.operator === 'length_between' ? '1' : 'any'} value={assertion.min} onChange={event => onUpdate(index, 'min', event.target.value)} /></Field><Field label="최댓값"><input type="number" min={assertion.operator === 'length_between' ? '0' : undefined} step={assertion.operator === 'length_between' ? '1' : 'any'} value={assertion.max} onChange={event => onUpdate(index, 'max', event.target.value)} /></Field>{assertion.operator === 'between' && <div className="assertion-boundaries"><label><input type="checkbox" checked={assertion.includeMin} onChange={event => onUpdate(index, 'includeMin', event.target.checked)} />최솟값 포함</label><label><input type="checkbox" checked={assertion.includeMax} onChange={event => onUpdate(index, 'includeMax', event.target.checked)} />최댓값 포함</label></div>}</div> : assertion.operator === 'type' ? <Field label="기대 타입"><select value={assertion.value || 'number'} onChange={event => onUpdate(index, 'value', event.target.value)}>{assertionTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field> : valueOperator ? <Field label="기준값"><input type="number" step="any" value={assertion.value} onChange={event => onUpdate(index, 'value', event.target.value)} /></Field> : <div className="assertion-no-value">추가 값 없이 경로만 검사합니다.</div>}
        <div className="assertion-row-actions"><button className="icon assertion-confirm" aria-label={`${index + 1}번째 조건 확인`} title={assertionCanConfirm(assertion) ? '입력 완료 및 조건 검증 활성화' : '조건 값을 모두 올바르게 입력하세요.'} disabled={!assertionCanConfirm(assertion)} onClick={() => onConfirm(index)}>✓</button><button className="icon danger" aria-label={`${index + 1}번째 조건 삭제`} title="조건 삭제" onClick={() => onRemove(index)}>×</button></div>
      </div>
    })}</div> : <div className="assertion-empty">등록된 조건이 없습니다. 기존 기대 응답 값 비교만 실행됩니다.</div>}
  </div>
}

function RunResult({ result }) {
  if (!result) return null
  const outputLines = asText(result.output).split('\n')
  const apiCallResults = outputLines.flatMap(line => {
    const value = line.trim().replace(/^actual_response=/, '')
    if (value === line.trim()) return []
    try { return [JSON.stringify(JSON.parse(value), null, 2)] } catch { return [value] }
  })
  const executionLog = outputLines.filter(line => !line.trim().startsWith('actual_response=')).join('\n')
  return <section className={`run-result ${result.error || result.exitCode ? 'failure' : 'success'}`}>
    <div className="result-heading"><strong>{result.error ? '실행 오류' : result.exitCode ? `실행 실패 (종료 코드 ${result.exitCode})` : '실행 완료'}</strong></div>
    {apiCallResults.length > 0 && <div style={{ padding: '14px', borderTop: '1px solid #dbe4f0', background: '#f8fbff' }}><strong style={{ color: '#334155', fontSize: 13 }}>API 호출 결과</strong><pre style={{ maxHeight: 260, margin: '10px 0 0', border: '1px solid #dbe4f0', borderRadius: 8 }}>{apiCallResults.map((value, index) => `${apiCallResults.length > 1 ? `호출 ${index + 1}\n` : ''}${value}`).join('\n\n')}</pre></div>}
    <div className="result-heading"><strong>실행 로그</strong></div>
    <pre>{result.error || executionLog}</pre>
  </section>
}

function TestSidebar({ active, projectRef, project, onNavigate, onProjectList }) {
  const projectName = project?.name || projectRef.replace(/\.json$/, '')
  return <aside className="sidebar"><button className="sidebar-back" onClick={onProjectList}>← 프로젝트 목록</button><div className="sidebar-title">현재 프로젝트</div><div className="current-project"><strong>{projectName}</strong>{project?.base_url && <code>{project.base_url}</code>}</div><div className="sidebar-title">테스트 구성</div><div className="side-nav"><button className={active === 'cases' ? 'active' : ''} onClick={() => onNavigate('cases')}>API 케이스</button><button className={active === 'pipeline' ? 'active' : ''} onClick={() => onNavigate('pipeline')}>파이프라인</button></div></aside>
}

function CaseList({ caseItems, projectRef, project, refresh, onNavigate, onProjectList, onCreate, onOpen }) {
  const [notice, setNotice] = useState('')
  const removeCase = async reference => {
    if (!window.confirm(`${reference} 케이스를 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    try { await api(`/api/cases/${encodeURIComponent(reference)}`, { method: 'DELETE' }); await refresh(); setNotice(`삭제됨: case/${reference}`) } catch (error) { setNotice(error.message) }
  }
  return <div className="workspace"><TestSidebar active="cases" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">API CASES</p><h2>API 케이스 목록 <span className="count">{caseItems.length}</span></h2></div><button className="primary" onClick={onCreate}>＋ 새 케이스</button></div>{caseItems.length ? <div className="case-list">{caseItems.map(reference => { const [tag, apiName, fileName] = reference.split('/'); return <article className="case-list-item" key={reference}><button className="case-list-row" onClick={() => onOpen(reference)}><span className="case-list-icon">{tag?.slice(0, 1).toUpperCase() || 'A'}</span><span><strong>{caseName(fileName) || reference}</strong><small>{tag} · {apiName}</small></span><span className="case-list-action">수정 · 실행 <b>→</b></span></button><button className="case-list-delete" aria-label={`${reference} 케이스 삭제`} title="케이스 삭제" onClick={() => removeCase(reference)}>×</button></article> })}</div> : <div className="empty">저장된 API 케이스가 없습니다. 새 케이스를 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main></div>
}

function CaseEditor({ refresh, projectRef, project, caseReference, onNavigate, onProjectList, onBack }) {
  const [form, setForm] = useState(newCaseForm)
  const [requestTab, setRequestTab] = useState('Params')
  const [selected, setSelected] = useState('')
  const [notice, setNotice] = useState('')
  const [result, setResult] = useState(null)
  const [savedCaseSignature, setSavedCaseSignature] = useState('')
  const [storageMeta, setStorageMeta] = useState(null)
  const [docOperations, setDocOperations] = useState([])
  const [docsExpanded, setDocsExpanded] = useState(false)
  const [projectVariablesExpanded, setProjectVariablesExpanded] = useState(false)
  const [caseVariablesExpanded, setCaseVariablesExpanded] = useState(false)
  const docsUrl = asText(project?.docs_url)
  const docsFile = project?.docs_file
  const docsDocument = docsFile?.document
  const docsSource = docsDocument
    ? { label: asText(docsFile?.name), request: { document: docsDocument } }
    : docsUrl ? { label: docsUrl, request: { url: docsUrl.trim() } } : null
  const plainProjectVariables = Object.keys(project?.variables?.plain || {})
  const secretProjectVariables = Object.keys(project?.variables?.secret || {})
  const availableProjectVariables = [
    ...plainProjectVariables.map(name => ({ name, secret: false })),
    ...secretProjectVariables.map(name => ({ name, secret: true })),
  ]
  const availableCaseVariables = form.secretVariables.filter(variable => asText(variable.name).trim())
  const copyProjectVariable = async name => {
    const reference = `{{project.${name}}}`
    try {
      await navigator.clipboard.writeText(reference)
      setNotice(`프로젝트 변수 참조를 복사했습니다: ${reference}`)
    } catch { setNotice(`프로젝트 변수 참조: ${reference}`) }
  }
  const copyCaseVariable = async name => {
    const reference = `{{case.${name}}}`
    try {
      await navigator.clipboard.writeText(reference)
      setNotice(`케이스 보안 변수 참조를 복사했습니다: ${reference}`)
    } catch { setNotice(`케이스 보안 변수 참조: ${reference}`) }
  }
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }))
  const caseRef = `${asText(form.tag)}/${asText(form.apiName)}/${jsonFileName(form.fileName)}`
  const responseVariables = responseVariablesFromJson(form.expectedBody)
  useEffect(() => {
    setResult(null)
    if (caseReference) load(caseReference)
    else { setForm(newCaseForm()); setSelected(''); setSavedCaseSignature(''); setStorageMeta(null); setNotice('새 API 케이스를 작성하세요.') }
  }, [caseReference, projectRef])

  const updateParam = (index, key, value) => setForm(current => {
    const params = current.params.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item)
    if (index === params.length - 1 && (params[index].key || params[index].value)) params.push({ key: '', value: '' })
    return { ...current, params }
  })
  const removeParam = index => setForm(current => ({ ...current, params: current.params.length === 1 ? [{ key: '', value: '' }] : current.params.filter((_, itemIndex) => itemIndex !== index) }))
  const updateFormData = (index, key, value) => setForm(current => ({
    ...current, formData: current.formData.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item),
  }))
  const removeFormData = index => setForm(current => ({ ...current, formData: current.formData.filter((_, itemIndex) => itemIndex !== index) }))
  const addCaseSecretVariable = () => setForm(current => ({ ...current, secretVariables: [...current.secretVariables, { name: '', value: '', configured: false }] }))
  const updateCaseSecretVariable = (index, key, value) => setForm(current => ({
    ...current,
    secretVariables: current.secretVariables.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item),
  }))
  const removeCaseSecretVariable = index => setForm(current => ({
    ...current,
    secretVariables: current.secretVariables.filter((_, itemIndex) => itemIndex !== index),
  }))
  const addAssertion = () => setForm(current => {
    const variable = responseVariables.find(item => !current.assertions.some(assertion => assertion.path === item.path)) || responseVariables[0]
    return { ...current, assertions: [...current.assertions, emptyAssertionRow(variable)] }
  })
  const selectAssertionVariable = (index, variable) => setForm(current => ({
    ...current,
    assertions: current.assertions.map((item, itemIndex) => {
      if (itemIndex !== index) return item
      if (!variable) return { ...item, path: '' }
      return emptyAssertionRow(variable)
    }),
  }))
  const updateAssertion = (index, key, value) => setForm(current => ({
    ...current,
    assertions: current.assertions.map((item, itemIndex) => {
      if (itemIndex !== index) return item
      if (key !== 'operator') return { ...item, [key]: value }
      return { ...item, operator: value, value: value === 'type' ? 'number' : '', min: '', max: '', includeMin: true, includeMax: true }
    }),
  }))
  const confirmAssertion = index => setForm(current => ({
    ...current, validateConditions: true,
    assertions: current.assertions.map((item, itemIndex) => itemIndex === index ? { ...item, confirmed: true } : item),
  }))
  const removeAssertion = index => setForm(current => ({ ...current, assertions: current.assertions.filter((_, itemIndex) => itemIndex !== index) }))

  const loadDocs = async (automatic = false) => {
    try {
      if (!docsSource) throw new Error('프로젝트 설정에서 OpenAPI/Swagger 문서 URL 또는 JSON 파일을 등록하세요.')
      const data = await api('/api/docs', { method: 'POST', body: JSON.stringify(docsSource.request) })
      setDocOperations(data.operations || [])
      setNotice(`${automatic ? '프로젝트 API 문서에서' : 'API 문서에서'} ${data.operations?.length || 0}개 API를 불러왔습니다.`)
    } catch (error) { setNotice(error.message) }
  }

  useEffect(() => {
    setDocOperations([])
    if (docsSource) loadDocs(true)
  }, [projectRef, docsUrl, docsDocument])

  const applyDocOperation = operationId => {
    const operation = docOperations.find(item => item.id === operationId)
    if (!operation) return
    let url = operation.path
    const queryParams = []
    const headers = []
    operation.parameters.forEach(parameter => {
      const value = docValue(parameter.value)
      if (parameter.in === 'path' && value) url = url.replaceAll(`{${parameter.name}}`, encodeURIComponent(value))
      if (parameter.in === 'query') queryParams.push({ key: parameter.name, value })
      if (parameter.in === 'header') headers.push(`${parameter.name}: ${value}`)
    })
    setForm(current => ({
      ...current, method: operation.method, url, params: [...queryParams, { key: '', value: '' }], headers: headers.join('\n'), bodyMode: 'json',
      body: operation.has_request_body ? JSON.stringify(operation.request_body, null, 2) : '', expectedStatus: String(operation.expected_status),
      expectedBody: operation.has_response_body ? JSON.stringify(operation.response_body, null, 2) : '', validateExact: operation.has_response_body,
    }))
    setRequestTab(operation.has_request_body ? 'Body' : 'Params')
    setNotice(`${operation.method} ${operation.path}의 요청 키와 기대 응답 예시를 적용했습니다.`)
  }

  const load = async reference => {
    if (!reference) return
    try {
      const data = await api(`/api/cases/${encodeURIComponent(reference)}`)
      // Cases created before path normalization on Windows may still use backslashes.
      const [tag, apiName, fileName] = asText(reference).split(/[\\/]/)
      const request = data.request || {}, expected = data.expected || {}, validationModes = expected.validation_modes || {}
      const requestUrl = splitRequestUrl(request.url)
      const headers = { ...(request.headers || {}) }
      const authorization = asText(headers.Authorization)
      delete headers.Authorization
      const formData = Array.isArray(request.form_data) ? request.form_data.map(item => ({
        key: asText(item?.key), kind: item?.file ? 'file' : 'text', value: item?.file ? '' : String(item?.value ?? ''), file: null,
        storedFile: asText(item?.file), filename: asText(item?.filename) || asText(item?.file).split('/').pop(), contentType: asText(item?.content_type),
      })) : []
      const secretVariables = Object.entries(data.variables?.secret || {}).map(([name, definition]) => ({
        name, value: '', configured: Boolean(definition?.configured),
      }))
      setForm({
        tag: asText(tag), apiName: asText(apiName), fileName: caseName(fileName), method: asText(request.method) || 'GET', url: requestUrl.baseUrl,
        params: requestUrl.params.concat({ key: '', value: '' }),
        authType: authorization.startsWith('Bearer ') ? 'Bearer Token' : 'No Auth', authValue: authorization.replace(/^Bearer /, ''),
        headers: Object.entries(headers).map(([key, value]) => `${key}: ${value}`).join('\n'),
        body: request.body === undefined ? '' : JSON.stringify(request.body, null, 2), bodyMode: Array.isArray(request.form_data) ? 'form-data' : 'json', formData, expectedStatus: String(expected.status ?? 200),
        strict: expected.strict ?? true, expectedBody: data._expectedBodyRaw ?? (expected.body === undefined ? '' : JSON.stringify(expected.body, null, 2)),
        validateExact: typeof validationModes.exact_body === 'boolean' ? validationModes.exact_body : expected.body !== undefined,
        validateConditions: typeof validationModes.conditions === 'boolean' ? validationModes.conditions : Array.isArray(expected.assertions) && expected.assertions.length > 0,
        assertions: Array.isArray(expected.assertions) ? expected.assertions.map(assertionFormRow) : [], secretVariables,
      })
      setSelected(reference); setStorageMeta(data._storage || null); setSavedCaseSignature(caseSignature(reference, data)); setNotice(''); setResult(null)
    } catch (error) { setNotice(error.message) }
  }

  const formDataDocument = async () => {
    const entries = form.formData.filter(item => item.key || item.value || item.file || item.storedFile)
    return Promise.all(entries.map(async (item, index) => {
      const key = asText(item.key).trim()
      if (!key) throw new Error(`form-data ${index + 1}번째 행의 Key를 입력하세요.`)
      if (item.kind !== 'file') return { key, value: asText(item.value) }
      let fileReference = asText(item.storedFile)
      if (item.file) {
        const safeName = `${index + 1}-${item.file.name.replace(/[\\/]/g, '_') || 'attachment'}`
        fileReference = await uploadAttachment(`${asText(form.tag).trim()}/${asText(form.apiName).trim()}/files/${safeName}`, item.file)
      }
      if (!fileReference) throw new Error(`form-data ${index + 1}번째 행에서 파일을 선택하세요.`)
      const attachment = { key, file: fileReference, filename: item.file?.name || asText(item.filename) || fileReference.split('/').pop() }
      const contentType = item.file?.type || asText(item.contentType)
      if (contentType) attachment.content_type = contentType
      return attachment
    }))
  }

  const document = async () => {
    if (!projectRef) throw new Error('프로젝트를 먼저 선택하세요.')
    if (!form.tag || !form.apiName || !form.fileName || !form.url) throw new Error('Tag, API 이름, 케이스 명, URL을 입력하세요.')
    const headers = parseHeaders(form.headers)
    if (form.authType === 'Bearer Token') {
      if (!form.authValue) throw new Error('Bearer Token을 입력하세요.')
      headers.Authorization = `Bearer ${form.authValue}`
    }
    const request = { method: form.method, url: appendParams(form.url, form.params) }
    if (Object.keys(headers).length) request.headers = headers
    if (form.bodyMode === 'form-data') request.form_data = await formDataDocument()
    else {
      const body = parseJson(form.body, 'Request body')
      if (body !== undefined) request.body = body
    }
    const expected = {
      status: Number(form.expectedStatus), strict: form.strict,
      validation_modes: { exact_body: form.validateExact, conditions: form.validateConditions },
    }
    if (!Number.isInteger(expected.status)) throw new Error('Expected status는 정수여야 합니다.')
    const expectedBody = parseJson(form.expectedBody, 'Expected body')
    if (form.validateExact && expectedBody === undefined) throw new Error('기대 응답 일치 검증을 사용하려면 Expected body를 입력하세요.')
    if (expectedBody !== undefined) expected.body = expectedBody
    if (form.validateConditions && !form.assertions.length) throw new Error('변수별 조건 검증을 사용하려면 조건을 하나 이상 추가하세요.')
    if (form.assertions.length) expected.assertions = form.assertions.map((assertion, index) => {
      const row = index + 1
      const path = asText(assertion.path).trim()
      if (!/^(?:\$\.)?(?:body(?:\.(?:[A-Za-z_][\w-]*|\d+))*|status)$/.test(path)) throw new Error(`조건 ${row}의 응답 경로는 body.age, body.items.0 또는 status 형식이어야 합니다.`)
      const result = { path, operator: assertion.operator }
      const numberValue = (value, label, integer = false) => {
        if (asText(value).trim() === '') throw new Error(`조건 ${row}의 ${label}을(를) 입력하세요.`)
        const parsed = Number(value)
        if (!Number.isFinite(parsed) || (integer && (!Number.isInteger(parsed) || parsed < 0))) throw new Error(`조건 ${row}의 ${label}은(는) ${integer ? '0 이상의 정수' : '숫자'}여야 합니다.`)
        return parsed
      }
      if (['gt', 'gte', 'lt', 'lte'].includes(assertion.operator)) result.value = numberValue(assertion.value, '기준값')
      if (assertion.operator === 'between' || assertion.operator === 'length_between') {
        const integer = assertion.operator === 'length_between'
        result.min = numberValue(assertion.min, '최솟값', integer)
        result.max = numberValue(assertion.max, '최댓값', integer)
        if (result.min > result.max) throw new Error(`조건 ${row}의 최솟값은 최댓값보다 클 수 없습니다.`)
        if (assertion.operator === 'between') {
          result.include_min = assertion.includeMin
          result.include_max = assertion.includeMax
        }
      }
      if (assertion.operator === 'type') result.value = assertion.value || 'number'
      return result
    })
    const secret = {}
    const names = new Set()
    form.secretVariables.forEach((item, index) => {
      const name = asText(item.name).trim()
      if (!name && !item.value && !item.configured) return
      if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(name)) throw new Error(`케이스 보안 변수 ${index + 1}의 변수명 형식이 올바르지 않습니다.`)
      if (names.has(name)) throw new Error(`중복된 케이스 보안 변수명입니다: ${name}`)
      names.add(name)
      if (item.value) secret[name] = { value: item.value }
      else if (item.configured) secret[name] = { preserve: true }
      else throw new Error(`케이스 보안 변수 ${name}의 값을 입력하세요.`)
    })
    return { project: projectRef, request, expected, variables: { secret } }
  }

  const casePayload = async () => ({ ...(await document()), _expectedBodyRaw: form.expectedBody })

  const save = async () => {
    try {
      const payload = await casePayload()
      const savePayload = selected === caseRef && storageMeta ? { ...payload, _storage: storageMeta } : payload
      const saved = await api(`/api/cases/${encodeURIComponent(caseRef)}`, { method: 'PUT', body: JSON.stringify(savePayload) })
      setStorageMeta(saved._storage || null)
      await refresh(); setSelected(caseRef); setSavedCaseSignature(caseSignature(caseRef, payload)); setNotice(`저장됨: case/${caseRef}`); return true
    } catch (error) { setNotice(error.message); return false }
  }
  const runOnly = async () => {
    try {
      const payload = await casePayload()
      const hasUnsavedChanges = caseSignature(caseRef, payload) !== savedCaseSignature
      setResult(null); setNotice(hasUnsavedChanges ? '현재 입력값을 저장하지 않고 실행 중입니다.' : '')
      setResult(await api('/api/run', { method: 'POST', body: JSON.stringify({ inlineCase: payload, caseReference: caseRef }) }))
      if (hasUnsavedChanges) setNotice('저장하지 않고 실행했습니다.')
    } catch (error) { setResult({ error: error.message }); setNotice(error.message) }
  }
  const removeCase = async () => {
    if (!selected) return setNotice('삭제할 저장된 케이스를 먼저 선택하세요.')
    if (!window.confirm(`${selected} 케이스를 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    try {
      await api(`/api/cases/${encodeURIComponent(selected)}`, { method: 'DELETE' })
      await refresh(); setForm(newCaseForm()); setSelected(''); setSavedCaseSignature(''); setStorageMeta(null); setResult(null); setNotice(`삭제됨: case/${selected}`)
    } catch (error) { setNotice(error.message) }
  }

  return <div className="workspace">
    <TestSidebar active="cases" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} />
    <main className="editor">
      <section className="card"><div className="section-header"><div><p className="eyebrow">CASE SETTINGS</p><h2>{selected ? 'API 케이스 설정' : '새 API 케이스'}</h2></div><div className="actions"><button className="ghost" onClick={onBack}>목록으로</button>{selected && <button className="danger-button" onClick={removeCase}>삭제</button>}<button className="ghost" onClick={save}>저장</button></div></div>
        <div className="form-grid three"><Field label="Tag"><input value={form.tag} onChange={event => set('tag', event.target.value)} /></Field><Field label="API 이름"><input value={form.apiName} onChange={event => set('apiName', event.target.value)} /></Field><Field label="케이스 명"><input value={form.fileName} onChange={event => set('fileName', event.target.value)} /></Field></div>
        <div className="case-resource-grid"><section className="docs-import"><div className="case-resource-heading"><div><p className="eyebrow">PROJECT API DOCUMENT</p><h3>프로젝트 API 문서</h3></div><button className="ghost icon variable-expand" aria-label={docsExpanded ? '프로젝트 API 문서 접기' : '프로젝트 API 문서 확장'} title={docsExpanded ? '접기' : '확장'} aria-expanded={docsExpanded} onClick={() => setDocsExpanded(current => !current)}>{docsExpanded ? '−' : '+'}</button></div>{docsExpanded && <div className="variable-panel-content">{docsSource ? <><div className="docs-source"><span>문서 원본</span><code>{docsSource.label}</code></div><button className="ghost" onClick={() => loadDocs()}>문서 새로 불러오기</button>{docOperations.length > 0 && <Field label="문서 API 선택" wide><select value="" onChange={event => applyDocOperation(event.target.value)}><option value="">API를 선택하세요. ({docOperations.length}개)</option>{docOperations.map(operation => <option key={operation.id} value={operation.id}>{operation.method} {operation.path}{operation.summary ? ` — ${operation.summary}` : ''}</option>)}</select></Field>}</> : <p className="hint">프로젝트 설정에서 OpenAPI / Swagger 문서 URL 또는 JSON 파일을 등록하면 API 목록을 자동으로 불러옵니다.</p>}<p className="hint">API를 선택하면 Params·Headers·Body와 기대 응답 예시가 자동 입력됩니다.</p></div>}</section>{availableProjectVariables.length > 0 && <section className="case-resource project-variable-reference"><div className="case-resource-heading"><div><p className="eyebrow">PROJECT VARIABLES</p><h3>프로젝트 공통 변수 <span className="count">{availableProjectVariables.length}</span></h3></div><button className="ghost icon variable-expand" aria-label={projectVariablesExpanded ? '프로젝트 공통 변수 접기' : '프로젝트 공통 변수 확장'} title={projectVariablesExpanded ? '접기' : '확장'} aria-expanded={projectVariablesExpanded} onClick={() => setProjectVariablesExpanded(current => !current)}>{projectVariablesExpanded ? '−' : '+'}</button></div>{projectVariablesExpanded && <div className="variable-panel-content"><p className="hint">URL·Params·Authorization·Headers·Body에서 참조식을 사용할 수 있습니다.</p><div className="project-variable-chips">{availableProjectVariables.map(variable => <button className={variable.secret ? 'secret' : ''} key={variable.name} onClick={() => copyProjectVariable(variable.name)}><span>{variable.secret ? '보안' : '일반'}</span><code>{`{{project.${variable.name}}}`}</code><small>복사</small></button>)}</div></div>}</section>}<section className="case-resource project-variable-reference"><div className="case-resource-heading"><div><p className="eyebrow">CASE SECRET VARIABLES</p><h3>케이스 전용 보안 변수 <span className="count">{availableCaseVariables.length}</span></h3></div><button className="ghost icon variable-expand" aria-label={caseVariablesExpanded ? '케이스 전용 보안 변수 접기' : '케이스 전용 보안 변수 확장'} title={caseVariablesExpanded ? '접기' : '확장'} aria-expanded={caseVariablesExpanded} onClick={() => setCaseVariablesExpanded(current => !current)}>{caseVariablesExpanded ? '−' : '+'}</button></div>{caseVariablesExpanded && <div className="variable-panel-content"><p className="hint">이 케이스에서만 사용할 API Key·토큰을 암호화해 저장합니다.</p><ProjectVariableRows secret items={form.secretVariables} onAdd={addCaseSecretVariable} onUpdate={updateCaseSecretVariable} onRemove={removeCaseSecretVariable} />{availableCaseVariables.length > 0 && <div className="project-variable-chips">{availableCaseVariables.map(variable => <button className="secret" key={variable.name} onClick={() => copyCaseVariable(variable.name)}><span>보안</span><code>{`{{case.${variable.name}}}`}</code><small>복사</small></button>)}</div>}</div>}</section></div>
      </section>
      <section className="card request-card"><div className="request-bar"><select className="method" value={form.method} onChange={event => set('method', event.target.value)}>{['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(method => <option key={method}>{method}</option>)}</select><input className="url-input" value={form.url} placeholder="/v1/users (프로젝트 Base URL 기준)" onChange={event => set('url', event.target.value)} /></div>
        <div className="tabs">{['Params', 'Authorization', 'Headers', 'Body'].map(tab => <button key={tab} className={requestTab === tab ? 'active' : ''} onClick={() => setRequestTab(tab)}>{tab}</button>)}</div>
        <div className="tab-content" style={requestTab === 'Params' ? { minHeight: 0, paddingBottom: 14 } : undefined}>{requestTab === 'Params' && <><div className="param-header"><span>Key</span><span>Value</span><span /></div>{form.params.map((param, index) => <div className="param-row" key={index}><input value={param.key} placeholder="page" onChange={event => updateParam(index, 'key', event.target.value)} /><input value={param.value} placeholder="1" onChange={event => updateParam(index, 'value', event.target.value)} /><button className="icon" onClick={() => removeParam(index)}>×</button></div>)}<button className="text-button" onClick={() => setForm(current => ({ ...current, params: [...current.params, { key: '', value: '' }] }))}>＋ Parameter 추가</button></>}
          {requestTab === 'Authorization' && <div className="auth-form"><Field label="Type"><select value={form.authType} onChange={event => set('authType', event.target.value)}><option>No Auth</option><option>Bearer Token</option></select></Field>{form.authType === 'Bearer Token' && <Field label="Token" wide><input type="password" value={form.authValue} onChange={event => set('authValue', event.target.value)} placeholder="토큰 값" /></Field>}</div>}
          {requestTab === 'Headers' && <JsonArea value={form.headers} onChange={value => set('headers', value)} placeholder={'Content-Type: application/json\nX-Request-Id: example'} />}
          {requestTab === 'Body' && <div><div className="body-mode"><button className={form.bodyMode === 'json' ? 'active' : ''} onClick={() => set('bodyMode', 'json')}>raw JSON</button><button className={form.bodyMode === 'form-data' ? 'active' : ''} onClick={() => set('bodyMode', 'form-data')}>form-data</button></div>{form.bodyMode === 'form-data' ? <><div className="form-data-header"><span>Key</span><span>Type</span><span>Value / File</span><span /></div>{form.formData.map((item, index) => <div className="form-data-row" key={index}><input value={item.key} placeholder="file" onChange={event => updateFormData(index, 'key', event.target.value)} /><select value={item.kind} onChange={event => updateFormData(index, 'kind', event.target.value)}><option value="text">Text</option><option value="file">File</option></select>{item.kind === 'file' ? <label className="file-picker"><input type="file" onChange={event => updateFormData(index, 'file', event.target.files?.[0] || null)} /><span>{item.file?.name || item.filename || '파일 선택'}</span></label> : <input value={item.value} placeholder="value" onChange={event => updateFormData(index, 'value', event.target.value)} />}<button className="icon" onClick={() => removeFormData(index)}>×</button></div>)}<button className="text-button" onClick={() => setForm(current => ({ ...current, formData: [...current.formData, emptyFormDataRow()] }))}>＋ form-data 추가</button><p className="hint">선택한 파일은 저장·재실행할 수 있도록 <code>case/{'{tag}'}/{'{api_name}'}/files/</code>에 보관됩니다. multipart Content-Type은 자동으로 설정됩니다.</p></> : <JsonArea value={form.body} onChange={value => set('body', value)} placeholder={'{\n  "name": "Ada"\n}'} />}</div>}
        </div>
      </section>
      <section className="card">
        <div className="section-header"><div><p className="eyebrow">ASSERTION</p><h2>기대 응답</h2></div></div>
        <div className="validation-method-section"><strong>검증 방법</strong><p className="hint">두 방법 중 하나만 선택하거나 둘 다 선택할 수 있습니다. Expected status는 선택과 관계없이 항상 검증합니다.</p><div className="validation-methods"><label className={`validation-method ${form.validateExact ? 'selected' : ''}`}><input type="checkbox" checked={form.validateExact} onChange={event => set('validateExact', event.target.checked)} /><span><strong>기대 응답 일치</strong><small>Expected body와 실제 응답의 값·구조를 비교합니다.</small></span></label><label className={`validation-method ${form.validateConditions ? 'selected' : ''}`}><input type="checkbox" checked={form.validateConditions} onChange={event => set('validateConditions', event.target.checked)} /><span><strong>변수별 조건</strong><small>선택한 변수의 범위·타입·존재·길이를 검사합니다.</small></span></label></div></div>
        <div className="expected-controls"><Field label="Expected status"><input value={form.expectedStatus} onChange={event => set('expectedStatus', event.target.value)} /></Field>{form.validateExact && <label className="toggle"><input type="checkbox" checked={form.strict} onChange={event => set('strict', event.target.checked)} /><span>strict 비교</span></label>}</div>
        {(form.validateExact || form.validateConditions) && <><div className="expected-body-heading"><strong>{form.validateExact ? form.validateConditions ? 'Expected body / 변수 예시 JSON' : 'Expected body' : '변수 예시 JSON'}</strong><span>{form.validateExact ? form.validateConditions ? '일치 검증과 변수 조건 선택에 사용' : '일치 검증에 사용' : '변수 조건 선택에 사용'}</span></div><JsonArea value={form.expectedBody} onChange={value => set('expectedBody', value)} placeholder={'{\n  "id": 1\n}'} /></>}
        {form.validateConditions && <AssertionEditor assertions={form.assertions} variables={responseVariables} enabled onAdd={addAssertion} onUpdate={updateAssertion} onConfirm={confirmAssertion} onSelectVariable={selectAssertionVariable} onRemove={removeAssertion} />}
      </section>
      <div className="case-run-action"><button className="primary" onClick={runOnly}>실행</button></div>
      {notice && <p className="notice">{notice}</p>}<RunResult result={result} onClose={() => setResult(null)} />
    </main>
  </div>
}

function PipelineList({ pipelineItems, projectRef, project, refresh, onNavigate, onProjectList, onCreate, onOpen }) {
  const [notice, setNotice] = useState('')
  const removePipeline = async reference => {
    if (!window.confirm(`${reference} 파이프라인을 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    try { await api(`/api/pipelines/${encodeURIComponent(reference)}`, { method: 'DELETE' }); await refresh(); setNotice(`삭제됨: pipelines/${reference}`) } catch (error) { setNotice(error.message) }
  }
  return <div className="workspace"><TestSidebar active="pipeline" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">PIPELINES</p><h2>파이프라인 목록 <span className="count">{pipelineItems.length}</span></h2></div><button className="primary" onClick={onCreate}>＋ 새 파이프라인</button></div>{pipelineItems.length ? <div className="case-list">{pipelineItems.map(reference => <article className="case-list-item" key={reference}><button className="case-list-row" onClick={() => onOpen(reference)}><span className="case-list-icon">P</span><span><strong>{reference.replace(/\.json$/, '')}</strong><small>{reference}</small></span><span className="case-list-action">수정 · 실행 <b>→</b></span></button><button className="case-list-delete" aria-label={`${reference} 파이프라인 삭제`} title="파이프라인 삭제" onClick={() => removePipeline(reference)}>×</button></article>)}</div> : <div className="empty">저장된 파이프라인이 없습니다. 새 파이프라인을 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main></div>
}

const newMappingDraft = () => ({ source_step: '', response_path: 'body.id', target: 'body', target_key: '', template: '{{value}}' })

function ValueMappingEditor({ editor, steps, onUpdateDraft, onAdd, onRemove, onSave, onCancel }) {
  const sourceSteps = steps.slice(0, editor.index)
  const draft = editor.draft
  const targetLabel = mapping => ({ url: 'URL', header: `Header: ${mapping.target_key}`, body: `Body: ${mapping.target_key}` }[mapping.target])
  return <section className="card mapping-card"><div className="section-header"><div><p className="eyebrow">VALUE TRANSFER</p><h2>{steps[editor.index]?.name} 요청에 값 전달</h2></div><div className="actions"><button className="ghost" onClick={onCancel}>닫기</button><button className="primary" onClick={onSave}>적용</button></div></div>{sourceSteps.length ? <><div className="mapping-grid"><Field label="A 단계"><select value={draft.source_step} onChange={event => onUpdateDraft('source_step', event.target.value)}><option value="">이전 단계 선택</option>{sourceSteps.map(step => <option key={step.name} value={step.name}>{step.name}</option>)}</select></Field><Field label="A 응답 경로"><input value={draft.response_path} onChange={event => onUpdateDraft('response_path', event.target.value)} placeholder="body.id 또는 status" /></Field><Field label="B 적용 위치"><select value={draft.target} onChange={event => onUpdateDraft('target', event.target.value)}><option value="url">Request URL</option><option value="header">Request Header</option><option value="body">Request Body</option></select></Field>{draft.target !== 'url' && <Field label="B 대상 키"><input value={draft.target_key} onChange={event => onUpdateDraft('target_key', event.target.value)} placeholder={draft.target === 'header' ? 'X-User-Id' : 'user.id'} /></Field>}<Field label="B 값 템플릿"><input value={draft.template} onChange={event => onUpdateDraft('template', event.target.value)} placeholder="/users/{{value}} 또는 Bearer {{value}}" /></Field></div><div className="step-actions"><p className="hint">A 값이 들어갈 위치에 <code>{'{{value}}'}</code>를 넣으세요. 예: <code>/users/{'{{value}}'}</code></p><button className="primary" onClick={onAdd}>＋ 값 전달 추가</button></div><div className="mapping-list">{editor.mappings.length ? editor.mappings.map((mapping, index) => <div className="mapping-item" key={`${mapping.source_step}-${mapping.response_path}-${index}`}><div><strong>{mapping.source_step}.response.{mapping.response_path}</strong><small>{targetLabel(mapping)} · {mapping.template}</small></div><button className="icon danger" title="값 전달 삭제" onClick={() => onRemove(index)}>×</button></div>) : <div className="empty">등록된 값 전달 설정이 없습니다.</div>}</div></> : <div className="empty">값을 전달할 이전 단계를 먼저 추가하세요.</div>}</section>
}

function PipelineEditor({ caseItems, refresh, projectRef, project, onNavigate, onProjectList, pipelineReference, onBack }) {
  const [fileName, setFileName] = useState('new_pipeline.json')
  const [defaults, setDefaults] = useState({ retry: 0, retry_interval_seconds: 0 })
  const [steps, setSteps] = useState([])
  const [draft, setDraft] = useState({ name: '', case: '', retry: '', interval: '', continue: false })
  const [selected, setSelected] = useState('')
  const [notice, setNotice] = useState('')
  const [result, setResult] = useState(null)
  const [mappingEditor, setMappingEditor] = useState(null)
  const [storageMeta, setStorageMeta] = useState(null)
  const ref = jsonFileName(fileName)
  useEffect(() => { if (!draft.case && caseItems.length) setDraft(current => ({ ...current, case: caseItems[0] })) }, [caseItems])
  useEffect(() => {
    setResult(null)
    if (pipelineReference) load(pipelineReference)
    else { setFileName('new_pipeline.json'); setDefaults({ retry: 0, retry_interval_seconds: 0 }); setSteps([]); setDraft({ name: '', case: '', retry: '', interval: '', continue: false }); setMappingEditor(null); setSelected(''); setStorageMeta(null); setNotice('새 파이프라인을 작성하세요.') }
  }, [pipelineReference, projectRef])
  const load = async reference => {
    if (!reference) return
    try { const data = await api(`/api/pipelines/${encodeURIComponent(reference)}`); setFileName(reference); setDefaults(data.defaults || { retry: 0, retry_interval_seconds: 0 }); setSteps(data.steps || []); setMappingEditor(null); setSelected(reference); setStorageMeta(data._storage || null); setNotice(`불러옴: ${reference}`); setResult(null) } catch (error) { setNotice(error.message) }
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
    try { const payload = pipelineDocument(); const saved = await api(`/api/pipelines/${encodeURIComponent(ref)}`, { method: 'PUT', body: JSON.stringify(selected === ref && storageMeta ? { ...payload, _storage: storageMeta } : payload) }); setStorageMeta(saved._storage || null); await refresh(); setSelected(ref); setNotice(`저장됨: pipelines/${ref}`); return true } catch (error) { setNotice(error.message); return false }
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
    if (!window.confirm(`${selected} 파이프라인을 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    try {
      await api(`/api/pipelines/${encodeURIComponent(selected)}`, { method: 'DELETE' })
      await refresh(); setFileName('new_pipeline.json'); setSteps([]); setMappingEditor(null); setSelected(''); setStorageMeta(null); setResult(null); setNotice(`삭제됨: pipelines/${selected}`)
    } catch (error) { setNotice(error.message) }
  }
  const move = (index, offset) => { setMappingEditor(null); setSteps(current => { const target = index + offset; if (target < 0 || target >= current.length) return current; const next = [...current]; [next[index], next[target]] = [next[target], next[index]]; return next }) }
  const openMappings = index => setMappingEditor({ index, mappings: steps[index].input_mappings || [], draft: newMappingDraft() })
  const updateMappingDraft = (key, value) => setMappingEditor(current => current ? { ...current, draft: { ...current.draft, [key]: value } } : current)
  const addMapping = () => {
    if (!mappingEditor) return
    const mapping = mappingEditor.draft
    const sourceSteps = steps.slice(0, mappingEditor.index)
    if (!sourceSteps.some(step => step.name === mapping.source_step)) return setNotice('값을 가져올 이전 단계를 선택하세요.')
    if (!/^(body(?:\.[\w-]+)*|status)$/.test(mapping.response_path)) return setNotice('응답 경로는 body.id 또는 status 형식이어야 합니다.')
    if (!mapping.template.includes('{{value}}')) return setNotice('값 템플릿에 {{value}}를 포함하세요.')
    if (mapping.target !== 'url' && !/^[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*$/.test(mapping.target_key)) return setNotice('Header 또는 Body 대상 키를 입력하세요.')
    const next = { source_step: mapping.source_step, response_path: mapping.response_path, target: mapping.target, template: mapping.template }
    if (mapping.target !== 'url') next.target_key = mapping.target_key
    setMappingEditor(current => current ? { ...current, mappings: [...current.mappings, next], draft: newMappingDraft() } : current)
  }
  const saveMappings = () => {
    if (!mappingEditor) return
    setSteps(current => current.map((step, index) => {
      if (index !== mappingEditor.index) return step
      const { input_mappings, ...withoutMappings } = step
      return mappingEditor.mappings.length ? { ...withoutMappings, input_mappings: mappingEditor.mappings } : withoutMappings
    }))
    setMappingEditor(null); setNotice('값 전달 설정을 적용했습니다.')
  }
  return <div className="workspace"><TestSidebar active="pipeline" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">PIPELINE SETTINGS</p><h2>{selected ? '파이프라인 설정' : '새 파이프라인'}</h2></div><div className="actions"><button className="ghost" onClick={onBack}>목록으로</button>{selected && <button className="danger-button" onClick={removePipeline}>삭제</button>}<button className="ghost" onClick={save}>저장</button><button className="ghost" onClick={runOnly}>실행만</button><button className="primary" onClick={run}>저장 후 실행</button></div></div><div className="form-grid three"><Field label="파일명"><input value={fileName} onChange={event => setFileName(event.target.value)} /></Field><Field label="기본 재시도"><input type="number" min="0" value={defaults.retry} onChange={event => setDefaults(current => ({ ...current, retry: event.target.value }))} /></Field><Field label="기본 간격 (초)"><input type="number" min="0" step="0.1" value={defaults.retry_interval_seconds} onChange={event => setDefaults(current => ({ ...current, retry_interval_seconds: event.target.value }))} /></Field></div></section><section className="card"><div className="section-header"><div><p className="eyebrow">ADD STEP</p><h2>테스트 단계 추가</h2></div></div><div className="form-grid step-grid"><Field label="케이스" wide><select value={draft.case} onChange={event => setDraft(current => ({ ...current, case: event.target.value }))} disabled={!projectRef}>{caseItems.map(item => <option key={item}>{item}</option>)}</select></Field><Field label="단계 이름"><input value={draft.name} onChange={event => setDraft(current => ({ ...current, name: event.target.value }))} placeholder="get_user" /></Field><Field label="재시도 (선택)"><input type="number" min="0" value={draft.retry} onChange={event => setDraft(current => ({ ...current, retry: event.target.value }))} /></Field><Field label="간격 (선택)"><input type="number" min="0" step="0.1" value={draft.interval} onChange={event => setDraft(current => ({ ...current, interval: event.target.value }))} /></Field></div><div className="step-actions"><label className="toggle"><input type="checkbox" checked={draft.continue} onChange={event => setDraft(current => ({ ...current, continue: event.target.checked }))} /><span>실패해도 다음 단계 실행</span></label><button className="primary" onClick={addStep}>＋ 단계 추가</button></div></section><section className="card"><div className="section-header"><div><p className="eyebrow">EXECUTION ORDER</p><h2>실행 순서 <span className="count">{steps.length}</span></h2></div></div><div className="steps">{steps.length ? steps.map((step, index) => <div className="step" key={step.name}><span className="order">{String(index + 1).padStart(2, '0')}</span><div><strong>{step.name}</strong><small>{step.case}{step.input_mappings?.length ? ` · 값 전달 ${step.input_mappings.length}개` : ''}</small></div><div className="step-meta">재시도 {step.retry ?? '기본값'} · 간격 {step.retry_interval_seconds ?? '기본값'}</div><div className="row-actions"><button className="mapping-button" onClick={() => openMappings(index)}>값 전달</button><button className="icon" onClick={() => move(index, -1)}>↑</button><button className="icon" onClick={() => move(index, 1)}>↓</button><button className="icon danger" onClick={() => setSteps(current => current.filter((_, itemIndex) => itemIndex !== index))}>×</button></div></div>) : <div className="empty">API 케이스를 먼저 저장한 뒤 단계로 추가하세요.</div>}</div></section>{mappingEditor && <ValueMappingEditor editor={mappingEditor} steps={steps} onUpdateDraft={updateMappingDraft} onAdd={addMapping} onRemove={index => setMappingEditor(current => current ? { ...current, mappings: current.mappings.filter((_, itemIndex) => itemIndex !== index) } : current)} onSave={saveMappings} onCancel={() => setMappingEditor(null)} />}{notice && <p className="notice">{notice}</p>}<RunResult result={result} onClose={() => setResult(null)} /></main></div>
}

function ProjectList({ projects, projectDetails, activeProject, onOpenProject, onCreateProject, onEditProject, refresh }) {
  const [notice, setNotice] = useState('')
  const removeProject = async reference => {
    if (!window.confirm(`${reference.replace(/\.json$/, '')} 프로젝트를 삭제할까요?\n연결된 파이프라인은 함께 목록에서 제거되며 변경 이력은 보관됩니다. 연결된 API 케이스가 있으면 먼저 케이스를 삭제해야 합니다.`)) return
    try {
      const result = await api(`/api/projects/${encodeURIComponent(reference)}`, { method: 'DELETE' })
      await refresh('')
      const pipelineNotice = result.deleted_pipelines?.length ? ` · 파이프라인 ${result.deleted_pipelines.length}개 함께 삭제` : ''
      setNotice(`삭제됨: projects/${reference}${pipelineNotice}`)
    } catch (error) { setNotice(error.message) }
  }
  return <main className="project-page"><section className="card project-list-card"><div className="section-header"><div><p className="eyebrow">SELECT PROJECT</p><h2>프로젝트 목록</h2></div><button className="primary" onClick={onCreateProject}>＋ 새 프로젝트 만들기</button></div>{projects.length ? <div className="project-grid">{projects.map(reference => <article className={`project-card ${activeProject === reference ? 'active' : ''}`} key={reference}><button className="project-card-open" onClick={() => onOpenProject(reference)}><span className="project-card-label">PROJECT</span><strong>{reference.replace(/\.json$/, '')}</strong><small>{projectDetails[reference]?.base_url || ''}</small><span className="project-card-action">API 테스트 열기 <b>→</b></span></button><div className="project-card-actions"><button className="project-card-edit" aria-label={`${reference} 프로젝트 수정`} title="프로젝트 수정" onClick={() => onEditProject(reference)}>수정</button><button className="project-card-delete" aria-label={`${reference} 프로젝트 삭제`} title="프로젝트 삭제" onClick={() => removeProject(reference)}>×</button></div></article>)}</div> : <div className="empty">등록된 프로젝트가 없습니다. 새 프로젝트를 만들어 시작하세요.</div>}</section>{notice && <p className="notice">{notice}</p>}</main>
}

const emptyProjectForm = () => ({
  name: '', baseUrl: '', docsUrl: '', docsFile: null, sameProxy: false, httpProxy: '', httpsProxy: '', verify: true,
  plainVariables: [], secretVariables: [],
})

function ProjectVariableRows({ secret = false, items, onAdd, onUpdate, onRemove }) {
  return <section className={`project-variable-group ${secret ? 'secret' : ''}`}>
    <div className="project-variable-heading"><div><strong>{secret ? '보안 변수' : '일반 변수'}</strong><p className="hint">{secret ? 'API Key·토큰처럼 노출되면 안 되는 값을 암호화해 저장합니다.' : '외부에 노출되어도 되는 프로젝트 공통값을 평문으로 저장합니다.'}</p></div><button className="ghost" onClick={onAdd}>＋ 변수 추가</button></div>
    {items.length ? <div className="project-variable-list"><div className="project-variable-header"><span>변수명</span><span>값</span><span /></div>{items.map((item, index) => <div className="project-variable-row" key={index}><input value={item.name} onChange={event => onUpdate(index, 'name', event.target.value)} placeholder={secret ? 'api_key' : 'tenant_id'} /><div className="project-variable-value"><input type={secret ? 'password' : 'text'} value={item.value} onChange={event => onUpdate(index, 'value', event.target.value)} placeholder={secret && item.configured ? '저장된 보안 값 유지' : '값 입력'} />{secret && item.configured && !item.value && <small>암호화된 값 저장됨</small>}</div><button className="icon danger" aria-label={`${index + 1}번째 ${secret ? '보안' : '일반'} 변수 삭제`} onClick={() => onRemove(index)}>×</button></div>)}</div> : <div className="project-variable-empty">등록된 {secret ? '보안' : '일반'} 변수가 없습니다.</div>}
  </section>
}

function ProjectSettings({ projects, projectReference, onSaved, onCancel }) {
  const [form, setForm] = useState(emptyProjectForm)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const [storageMeta, setStorageMeta] = useState(null)
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }))
  const setSameProxy = checked => setForm(current => {
    const commonProxy = current.httpProxy || current.httpsProxy
    return { ...current, sameProxy: checked, httpProxy: checked ? commonProxy : current.httpProxy, httpsProxy: checked ? commonProxy : current.httpsProxy }
  })
  const setCommonProxy = value => setForm(current => ({ ...current, httpProxy: value, httpsProxy: value }))
  const addVariable = kind => setForm(current => ({ ...current, [kind]: [...current[kind], { name: '', value: '', configured: false }] }))
  const updateVariable = (kind, index, key, value) => setForm(current => ({ ...current, [kind]: current[kind].map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item) }))
  const removeVariable = (kind, index) => setForm(current => ({ ...current, [kind]: current[kind].filter((_, itemIndex) => itemIndex !== index) }))
  const setDocsUrl = value => setForm(current => ({ ...current, docsUrl: value, docsFile: value ? null : current.docsFile }))
  const selectDocsFile = async event => {
    const input = event.target
    const file = input.files?.[0]
    if (!file) return
    try {
      if (!file.name.toLowerCase().endsWith('.json')) throw new Error('OpenAPI / Swagger 문서는 JSON 파일만 선택할 수 있습니다.')
      if (file.size > 5 * 1024 * 1024) throw new Error('OpenAPI / Swagger JSON 파일은 5MB 이하여야 합니다.')
      const document = JSON.parse(await file.text())
      const data = await api('/api/docs', { method: 'POST', body: JSON.stringify({ document }) })
      setForm(current => ({ ...current, docsUrl: '', docsFile: { name: file.name, document } }))
      setNotice(`${file.name}에서 ${data.operations?.length || 0}개 API를 확인했습니다.`)
    } catch (error) { setNotice(error instanceof SyntaxError ? '올바른 JSON 파일이 아닙니다.' : error.message) }
    finally { input.value = '' }
  }
  const isEditing = Boolean(projectReference)
  useEffect(() => {
    if (!projectReference) { setForm(emptyProjectForm()); setAdvancedOpen(false); setStorageMeta(null); setNotice(''); return }
    const load = async () => {
      try {
        const data = await api(`/api/projects/${encodeURIComponent(projectReference)}`)
        const advanced = data.advanced || {}
        const legacyProxy = asText(advanced.proxy)
        const httpProxy = asText(advanced.http_proxy) || legacyProxy
        const httpsProxy = asText(advanced.https_proxy) || legacyProxy
        const variables = data.variables || {}
        const plainVariables = Object.entries(variables.plain || {}).map(([name, value]) => ({ name, value: asText(value), configured: false }))
        const secretVariables = Object.entries(variables.secret || {}).map(([name, definition]) => ({ name, value: '', configured: Boolean(definition?.configured) }))
        const docsFile = data.docs_file?.document ? data.docs_file : null
        setForm({ name: asText(data.name), baseUrl: asText(data.base_url), docsUrl: asText(data.docs_url), docsFile, sameProxy: Boolean(httpProxy && httpProxy === httpsProxy), httpProxy, httpsProxy, verify: advanced.verify ?? true, plainVariables, secretVariables })
        setStorageMeta(data._storage || null)
        setAdvancedOpen(Boolean(httpProxy || httpsProxy || docsFile || plainVariables.length || secretVariables.length) || advanced.verify === false); setNotice('')
      } catch (error) { setNotice(error.message) }
    }
    load()
  }, [projectReference])
  const save = async () => {
    try {
      if (!form.name || !form.baseUrl) throw new Error('프로젝트 이름과 Base URL을 입력하세요.')
      const variableNamePattern = /^[A-Za-z_][A-Za-z0-9_-]*$/
      const plain = {}, secret = {}, names = new Set()
      form.plainVariables.forEach((item, index) => {
        const name = asText(item.name).trim()
        if (!name && !item.value) return
        if (!variableNamePattern.test(name)) throw new Error(`일반 변수 ${index + 1}의 변수명 형식이 올바르지 않습니다.`)
        if (names.has(name)) throw new Error(`중복된 프로젝트 변수명입니다: ${name}`)
        names.add(name); plain[name] = asText(item.value)
      })
      form.secretVariables.forEach((item, index) => {
        const name = asText(item.name).trim()
        if (!name && !item.value && !item.configured) return
        if (!variableNamePattern.test(name)) throw new Error(`보안 변수 ${index + 1}의 변수명 형식이 올바르지 않습니다.`)
        if (names.has(name)) throw new Error(`중복된 프로젝트 변수명입니다: ${name}`)
        names.add(name)
        if (item.value) secret[name] = { value: item.value }
        else if (item.configured) secret[name] = { preserve: true }
        else throw new Error(`보안 변수 ${name}의 값을 입력하세요.`)
      })
      const reference = projectReference || projectFileName(form.name, projects)
      const payload = { name: form.name, base_url: form.baseUrl, docs_url: form.docsUrl, advanced: { http_proxy: form.httpProxy, https_proxy: form.httpsProxy, verify: form.verify }, variables: { plain, secret } }
      if (form.docsFile) payload.docs_file = form.docsFile
      await api(`/api/projects/${encodeURIComponent(reference)}`, { method: 'PUT', body: JSON.stringify(projectReference && storageMeta ? { ...payload, _storage: storageMeta } : payload) })
      await onSaved(reference)
    } catch (error) { setNotice(error.message) }
  }
  return <main className="project-page"><section className="card"><div className="section-header"><div><p className="eyebrow">{isEditing ? 'EDIT PROJECT' : 'NEW PROJECT'}</p><h2>프로젝트 설정</h2></div><div className="actions"><button className="ghost" onClick={onCancel}>목록으로</button><button className="primary" onClick={save}>저장</button></div></div><div className="form-grid project-settings-grid"><Field label="프로젝트 이름"><input value={form.name} onChange={event => set('name', event.target.value)} placeholder="New Project" /></Field><Field label="Base URL"><input value={form.baseUrl} onChange={event => set('baseUrl', event.target.value)} placeholder="https://api.example.com" /></Field></div><section className="advanced-settings"><button className="advanced-toggle" onClick={() => setAdvancedOpen(current => !current)}><span>설정</span><span>{advancedOpen ? '−' : '+'}</span></button>{advancedOpen && <div className="advanced-content"><section className="proxy-settings"><div className="proxy-settings-heading"><strong>OpenAPI 설정</strong></div><div className="openapi-source-options"><Field label="OpenAPI / Swagger 문서 URL"><input value={form.docsUrl} onChange={event => setDocsUrl(event.target.value)} placeholder="https://api.example.com/openapi.json" /></Field><span className="openapi-or">또는</span><div className="field"><span>OpenAPI / Swagger JSON 파일</span><div className="openapi-file-input"><label className="file-picker"><input type="file" accept=".json,application/json" onChange={selectDocsFile} /><span>{form.docsFile?.name || 'JSON 파일 선택'}</span></label>{form.docsFile && <button className="ghost" onClick={() => setForm(current => ({ ...current, docsFile: null }))}>제거</button>}</div></div></div><p className="hint">문서 URL과 JSON 파일 중 하나를 등록할 수 있습니다. 저장하면 이 프로젝트의 API 케이스 설정에서 자동으로 불러옵니다.</p></section><section className="project-variable-settings"><div className="proxy-settings-heading"><div><strong>프로젝트 공통 변수</strong><p className="hint">API 케이스에서 <code>{'{{project.변수명}}'}</code>으로 불러옵니다.</p></div></div><ProjectVariableRows items={form.plainVariables} onAdd={() => addVariable('plainVariables')} onUpdate={(index, key, value) => updateVariable('plainVariables', index, key, value)} onRemove={index => removeVariable('plainVariables', index)} /><ProjectVariableRows secret items={form.secretVariables} onAdd={() => addVariable('secretVariables')} onUpdate={(index, key, value) => updateVariable('secretVariables', index, key, value)} onRemove={index => removeVariable('secretVariables', index)} /></section><section className="proxy-settings"><div className="proxy-settings-heading"><strong>Proxy 설정</strong></div>{form.sameProxy ? <Field label="Proxy URL (HTTP/HTTPS)"><input value={form.httpProxy} onChange={event => setCommonProxy(event.target.value)} placeholder="http://proxy.example.com:8080" /></Field> : <div className="form-grid project-settings-grid"><Field label="HTTP Proxy URL"><input value={form.httpProxy} onChange={event => set('httpProxy', event.target.value)} placeholder="http://proxy.example.com:8080" /></Field><Field label="HTTPS Proxy URL"><input value={form.httpsProxy} onChange={event => set('httpsProxy', event.target.value)} placeholder="http://proxy.example.com:8080" /></Field></div>}<label className="toggle"><input type="checkbox" checked={form.sameProxy} onChange={event => setSameProxy(event.target.checked)} /><span>HTTP/HTTPS 공통 주소 사용</span></label><p className="hint">HTTP 또는 HTTPS 프록시 주소가 입력되어 있으면 해당 프로토콜 요청에 자동 적용됩니다. 두 주소를 모두 비우면 직접 연결합니다. 많은 사내 프록시는 HTTPS 요청에도 <code>http://</code> 형식의 프록시 주소를 사용합니다.</p></section><label className="toggle"><input type="checkbox" checked={form.verify} onChange={event => set('verify', event.target.checked)} /><span>TLS 인증서 검증 (verify)</span></label><p className="hint">verify를 끄면 자체 서명 인증서 등의 TLS 검증을 생략합니다.</p></div>}</section><p className="hint">{isEditing ? <>프로젝트 파일명 <code>{projectReference}</code>은 유지됩니다. 변경한 Base URL, API 문서와 공통 변수는 연결된 API 케이스와 파이프라인 실행에 즉시 적용됩니다.</> : <>프로젝트 JSON 파일은 프로젝트 이름을 기준으로 자동 생성됩니다. 케이스의 URL·Params·Authorization·Headers·Body에서 <code>{'{{project.변수명}}'}</code>을 사용할 수 있습니다.</>}</p></section>{notice && <p className="notice">{notice}</p>}</main>
}

function StudioApp() {
  const [tab, setTab] = useState('project')
  const [projects, setProjects] = useState([])
  const [projectDetails, setProjectDetails] = useState({})
  const [activeProject, setActiveProject] = useState('')
  const [project, setProject] = useState(null)
  const [projectSettingsReference, setProjectSettingsReference] = useState('')
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
      setProjects(projectData.items); setProjectDetails(projectData.details || {}); setActiveProject(selectedProject); setProject(selectedDocument); setCaseItems(cases.items); setPipelineItems(pipelines.items); setError('')
    } catch (requestError) { setError(`서버 연결 오류: ${requestError.message}`) }
  }
  const selectProject = async reference => { setCaseReference(''); setPipelineReference(''); await refresh(reference) }
  const openProject = async reference => { await selectProject(reference); setTab('case-list') }
  const saveProjectAndOpen = async reference => { await openProject(reference) }
  const createProject = () => { setProjectSettingsReference(''); setTab('project-settings') }
  const editProject = reference => { setProjectSettingsReference(reference); setTab('project-settings') }
  const navigateTest = target => {
    if (target === 'cases') { setCaseReference(''); setTab('case-list') }
    else { setPipelineReference(''); setTab('pipeline-list') }
  }
  const openCase = reference => { setCaseReference(reference); setTab('case-settings') }
  const createCase = () => { setCaseReference(''); setTab('case-settings') }
  const openPipeline = reference => { setPipelineReference(reference); setTab('pipeline-settings') }
  const createPipeline = () => { setPipelineReference(''); setTab('pipeline-settings') }
  useEffect(() => { refresh() }, [])
  const editorProps = { caseItems, pipelineItems, projectRef: activeProject, project, refresh, onNavigate: navigateTest, onProjectList: () => setTab('project') }
  return <><header className="topbar"><div className="brand"><img className="brand-logo" src="/logo.png" alt="API Develop Studio" /><div><strong>API Develop Studio</strong></div></div><nav><button className={tab === 'project' || tab === 'project-settings' ? 'selected' : ''} onClick={() => setTab('project')}>API 검증</button></nav><button className="ghost refresh" onClick={() => refresh()}>↻ 새로고침</button></header>{error && <div className="connection-error">{error} — Python 서버를 먼저 실행하세요: <code>python3 react_server.py</code></div>}{tab === 'project' ? <ProjectList projects={projects} projectDetails={projectDetails} activeProject={activeProject} onOpenProject={openProject} onCreateProject={createProject} onEditProject={editProject} refresh={refresh} /> : tab === 'project-settings' ? <ProjectSettings projects={projects} projectReference={projectSettingsReference} onSaved={saveProjectAndOpen} onCancel={() => setTab('project')} /> : tab === 'case-list' ? <CaseList {...editorProps} onCreate={createCase} onOpen={openCase} /> : tab === 'case-settings' ? <CaseEditor {...editorProps} caseReference={caseReference} onBack={() => navigateTest('cases')} /> : tab === 'pipeline-list' ? <PipelineList {...editorProps} onCreate={createPipeline} onOpen={openPipeline} /> : <PipelineEditor {...editorProps} pipelineReference={pipelineReference} onBack={() => navigateTest('pipeline')} />}</>
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
