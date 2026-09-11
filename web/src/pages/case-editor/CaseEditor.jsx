import { ProjectVariableRows } from '../../components/ProjectVariableRows.jsx'
import { Field } from '../../components/Field.jsx'
import { authorizationTypes, AuthorizationEditor } from '../../components/AuthorizationEditor.jsx'
import { JsonArea } from '../../components/JsonArea.jsx'
import { AssertionEditor } from './AssertionEditor.jsx'
import { RunResult } from '../../components/RunResult.jsx'
import { TestSidebar } from '../../components/ProjectSidebar.jsx'
import { asText, docValue, emptyFormDataRow, emptyAssertionRow, stringFormats, assertionFormRow, newCaseForm, responseVariablesFromJson, jsonFileName, caseName, groupDocOperationsByTag, api, uploadAttachment, parseJson, parseHeaders, caseSignature, splitRequestUrl, appendParams } from '../../utils/studio.js'
import { useEffect, useState } from 'react'

function CaseEditor({ refresh, projectRef, project, caseReference, onNavigate, onProjectList, onBack }) {
  const [form, setForm] = useState(newCaseForm)
  const [requestTab, setRequestTab] = useState('Params')
  const [selected, setSelected] = useState('')
  const [notice, setNotice] = useState('')
  const [result, setResult] = useState(null)
  const [savedCaseSignature, setSavedCaseSignature] = useState('')
  const [storageMeta, setStorageMeta] = useState(null)
  const [docOperations, setDocOperations] = useState([])
  const [selectedDocOperationId, setSelectedDocOperationId] = useState('')
  const [docsExpanded, setDocsExpanded] = useState(false)
  const [projectVariablesExpanded, setProjectVariablesExpanded] = useState(false)
  const [caseVariablesExpanded, setCaseVariablesExpanded] = useState(false)
  const docsUrl = asText(project?.docs_url)
  const docsFile = project?.docs_file
  const docsDocument = docsFile?.document
  const docsBundle = project?.docs_bundle
  const noProxy = project?.advanced?.use_proxy === false
  const docsSource = docsBundle
    ? { label: `${docsBundle.entrypoint} · ${Object.keys(docsBundle.files || {}).length}개 파일`, request: { bundle: docsBundle, for_case: true } }
    : docsDocument
    ? { label: asText(docsFile?.name), request: { document: docsDocument, for_case: true } }
    : docsUrl ? { label: docsUrl, request: { url: docsUrl.trim(), no_proxy: noProxy, for_case: true } } : null
  const plainProjectVariables = Object.keys(project?.variables?.plain || {})
  const secretProjectVariables = Object.keys(project?.variables?.secret || {})
  const availableProjectVariables = [
    ...plainProjectVariables.map(name => ({ name, secret: false })),
    ...secretProjectVariables.map(name => ({ name, secret: true })),
  ]
  const availableCaseVariables = form.secretVariables.filter(variable => asText(variable.name).trim())
  const additionalBaseUrls = Array.isArray(project?.base_urls)
    ? project.base_urls.filter(item => item && typeof item.name === 'string' && typeof item.url === 'string')
    : []
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
      return { ...item, operator: value, value: value === 'type' ? 'number' : '', format: 'none', pattern: '', min: '', max: '', includeMin: true, includeMax: true }
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
      setSelectedDocOperationId('')
      setNotice(`${automatic ? '프로젝트 API 문서에서' : 'API 문서에서'} ${data.operations?.length || 0}개 API를 불러왔습니다.`)
    } catch (error) { setNotice(error.message) }
  }

  useEffect(() => {
    setDocOperations([])
    if (docsSource) loadDocs(true)
  }, [projectRef, docsUrl, docsDocument, noProxy])

  const applyDocOperation = operationId => {
    const operation = docOperations.find(item => item.id === operationId)
    if (!operation) return
    setSelectedDocOperationId(operationId)
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
      const storedAuth = request.auth && typeof request.auth === 'object'
        ? request.auth
        : authorization.startsWith('Bearer ') ? { type: 'Bearer Token', token: authorization.replace(/^Bearer /, '') } : { type: 'No Auth' }
      if (!request.auth && authorization.startsWith('Bearer ')) delete headers.Authorization
      const { type: loadedAuthType = 'No Auth', ...loadedAuthValues } = storedAuth
      const formData = Array.isArray(request.form_data) ? request.form_data.map(item => ({
        key: asText(item?.key), kind: item?.file ? 'file' : 'text', value: item?.file ? '' : String(item?.value ?? ''), file: null,
        storedFile: asText(item?.file), filename: asText(item?.filename) || asText(item?.file).split('/').pop(), contentType: asText(item?.content_type),
      })) : []
      const secretVariables = Object.entries(data.variables?.secret || {}).map(([name, definition]) => ({
        name, value: '', configured: Boolean(definition?.configured),
      }))
      setForm({
        tag: asText(tag), apiName: asText(apiName), fileName: caseName(fileName), method: asText(request.method) || 'GET', url: requestUrl.baseUrl,
        baseUrlName: asText(data.base_url_name),
        timeout: data.timeout === undefined ? '' : String(data.timeout), params: requestUrl.params.concat({ key: '', value: '' }),
        maxResponseTimeMs: expected.max_response_time_ms === undefined ? '' : String(expected.max_response_time_ms),
        authType: authorizationTypes.includes(loadedAuthType) ? loadedAuthType : 'No Auth', authValues: loadedAuthValues,
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
    const request = { method: form.method, url: appendParams(form.url, form.params), auth: { type: form.authType, ...form.authValues } }
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
    const timeoutText = asText(form.timeout).trim()
    const responseTimeText = asText(form.maxResponseTimeMs).trim()
    if (responseTimeText) {
      const limit = Number(responseTimeText)
      if (!Number.isFinite(limit) || limit <= 0) throw new Error('최대 응답 시간은 0보다 큰 숫자여야 합니다.')
      expected.max_response_time_ms = limit
    }
    const timeout = timeoutText ? Number(timeoutText) : undefined
    if (timeout !== undefined && (!Number.isFinite(timeout) || timeout <= 0)) throw new Error('API timeout은 0보다 큰 초 단위 숫자여야 합니다.')
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
      if (assertion.operator === 'type') {
        result.value = assertion.value || 'number'
        if (result.value === 'string') {
          result.format = assertion.format || 'none'
          if (!stringFormats.some(([value]) => value === result.format)) throw new Error(`조건 ${row}의 문자열 format을 선택하세요.`)
          if (result.format === 'custom') {
            result.pattern = asText(assertion.pattern).trim()
            if (!result.pattern) throw new Error(`조건 ${row}의 정규식을 입력하세요.`)
          }
        }
      }
      if (assertion.operator === 'format') {
        result.value = assertion.value || 'none'
        if (!stringFormats.some(([value]) => value === result.value)) throw new Error(`조건 ${row}의 형식을 선택하세요.`)
        if (result.value === 'custom') {
          result.pattern = asText(assertion.pattern).trim()
          if (!result.pattern) throw new Error(`조건 ${row}의 정규식을 입력하세요.`)
        }
      }
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
    return { project: projectRef, ...(form.baseUrlName ? { base_url_name: form.baseUrlName } : {}), ...(timeout === undefined ? {} : { timeout }), request, expected, variables: { secret } }
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
        <div className="form-grid three"><Field label="Tag"><input value={form.tag} onChange={event => set('tag', event.target.value)} /></Field><Field label="API 이름"><input value={form.apiName} onChange={event => set('apiName', event.target.value)} /></Field><Field label="케이스 명"><input value={form.fileName} onChange={event => set('fileName', event.target.value)} /></Field></div><div className="case-timeout"><Field label="API timeout (초)"><input type="number" min="0.1" step="0.1" value={form.timeout} onChange={event => set('timeout', event.target.value)} placeholder="기본값 (10)" /></Field></div>
        <div className="case-resource-grid"><section className="docs-import"><div className="case-resource-heading"><div><p className="eyebrow">PROJECT API DOCUMENT</p><h3>프로젝트 API 문서</h3></div><button className="ghost icon variable-expand" aria-label={docsExpanded ? '프로젝트 API 문서 접기' : '프로젝트 API 문서 확장'} title={docsExpanded ? '접기' : '확장'} aria-expanded={docsExpanded} onClick={() => setDocsExpanded(current => !current)}>{docsExpanded ? '−' : '+'}</button></div>{docsExpanded && <div className="variable-panel-content">{docsSource ? <><div className="docs-source"><span>문서 원본</span><code>{docsSource.label}</code></div><button className="ghost" onClick={() => loadDocs()}>문서 새로 불러오기</button>{docOperations.length > 0 && <Field label="문서 API 선택" wide><select className="document-operation-select" value={selectedDocOperationId} onChange={event => applyDocOperation(event.target.value)}><option value="">API를 선택하세요. ({docOperations.length}개)</option>{groupDocOperationsByTag(docOperations).map(([tag, operations]) => <optgroup key={tag} label={`${tag} (${operations.length})`}>{operations.map(operation => <option key={operation.id} value={operation.id}>{operation.method} {operation.path}</option>)}</optgroup>)}</select></Field>}</> : <p className="hint">프로젝트 설정에서 OpenAPI / Swagger 문서 URL 또는 JSON 파일을 등록하면 API 목록을 자동으로 불러옵니다.</p>}<p className="hint">API를 선택하면 Params·Headers·Body와 기대 응답 예시가 자동 입력됩니다.</p></div>}</section>{availableProjectVariables.length > 0 && <section className="case-resource project-variable-reference"><div className="case-resource-heading"><div><p className="eyebrow">PROJECT VARIABLES</p><h3>프로젝트 공통 변수 <span className="count">{availableProjectVariables.length}</span></h3></div><button className="ghost icon variable-expand" aria-label={projectVariablesExpanded ? '프로젝트 공통 변수 접기' : '프로젝트 공통 변수 확장'} title={projectVariablesExpanded ? '접기' : '확장'} aria-expanded={projectVariablesExpanded} onClick={() => setProjectVariablesExpanded(current => !current)}>{projectVariablesExpanded ? '−' : '+'}</button></div>{projectVariablesExpanded && <div className="variable-panel-content"><p className="hint">URL·Params·Authorization·Headers·Body에서 참조식을 사용할 수 있습니다.</p><div className="project-variable-chips">{availableProjectVariables.map(variable => <button className={variable.secret ? 'secret' : ''} key={variable.name} onClick={() => copyProjectVariable(variable.name)}><span>{variable.secret ? '보안' : '일반'}</span><code>{`{{project.${variable.name}}}`}</code><small>복사</small></button>)}</div></div>}</section>}<section className="case-resource project-variable-reference"><div className="case-resource-heading"><div><p className="eyebrow">CASE SECRET VARIABLES</p><h3>케이스 전용 보안 변수 <span className="count">{availableCaseVariables.length}</span></h3></div><button className="ghost icon variable-expand" aria-label={caseVariablesExpanded ? '케이스 전용 보안 변수 접기' : '케이스 전용 보안 변수 확장'} title={caseVariablesExpanded ? '접기' : '확장'} aria-expanded={caseVariablesExpanded} onClick={() => setCaseVariablesExpanded(current => !current)}>{caseVariablesExpanded ? '−' : '+'}</button></div>{caseVariablesExpanded && <div className="variable-panel-content"><p className="hint">이 케이스에서만 사용할 API Key·토큰을 암호화해 저장합니다.</p><ProjectVariableRows secret items={form.secretVariables} onAdd={addCaseSecretVariable} onUpdate={updateCaseSecretVariable} onRemove={removeCaseSecretVariable} />{availableCaseVariables.length > 0 && <div className="project-variable-chips">{availableCaseVariables.map(variable => <button className="secret" key={variable.name} onClick={() => copyCaseVariable(variable.name)}><span>보안</span><code>{`{{case.${variable.name}}}`}</code><small>복사</small></button>)}</div>}</div>}</section></div>
      </section>
      <section className="card request-card"><div className="request-bar"><select className="base-url-select" aria-label="Base URL 선택" title="Base URL 선택" value={form.baseUrlName} onChange={event => set('baseUrlName', event.target.value)}><option value="">기본 · {asText(project?.base_url)}</option>{additionalBaseUrls.map(item => <option key={item.name} value={item.name}>{item.name} · {item.url}</option>)}</select><select className="method" value={form.method} onChange={event => set('method', event.target.value)}>{['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(method => <option key={method}>{method}</option>)}</select><input className="url-input" value={form.url} placeholder="/v1/users (선택한 Base URL 기준)" onChange={event => set('url', event.target.value)} /></div>
        <div className="tabs">{['Params', 'Authorization', 'Headers', 'Body'].map(tab => <button key={tab} className={requestTab === tab ? 'active' : ''} onClick={() => setRequestTab(tab)}>{tab}</button>)}</div>
        <div className="tab-content" style={requestTab === 'Params' ? { minHeight: 0, paddingBottom: 14 } : undefined}>{requestTab === 'Params' && <><div className="param-header"><span>Key</span><span>Value</span><span /></div>{form.params.map((param, index) => <div className="param-row" key={index}><input value={param.key} placeholder="page" onChange={event => updateParam(index, 'key', event.target.value)} /><input value={param.value} placeholder="1" onChange={event => updateParam(index, 'value', event.target.value)} /><button className="icon" onClick={() => removeParam(index)}>×</button></div>)}<button className="text-button" onClick={() => setForm(current => ({ ...current, params: [...current.params, { key: '', value: '' }] }))}>＋ Parameter 추가</button></>}
          {requestTab === 'Authorization' && <AuthorizationEditor type={form.authType} values={form.authValues} onTypeChange={value => setForm(current => ({ ...current, authType: value, authValues: {} }))} onValueChange={(key, value) => setForm(current => ({ ...current, authValues: { ...current.authValues, [key]: value } }))} />}
          {requestTab === 'Headers' && <JsonArea value={form.headers} onChange={value => set('headers', value)} placeholder={'Content-Type: application/json\nX-Request-Id: example'} />}
          {requestTab === 'Body' && <div><div className="body-mode"><button className={form.bodyMode === 'json' ? 'active' : ''} onClick={() => set('bodyMode', 'json')}>raw JSON</button><button className={form.bodyMode === 'form-data' ? 'active' : ''} onClick={() => set('bodyMode', 'form-data')}>form-data</button></div>{form.bodyMode === 'form-data' ? <><div className="form-data-header"><span>Key</span><span>Type</span><span>Value / File</span><span /></div>{form.formData.map((item, index) => <div className="form-data-row" key={index}><input value={item.key} placeholder="file" onChange={event => updateFormData(index, 'key', event.target.value)} /><select value={item.kind} onChange={event => updateFormData(index, 'kind', event.target.value)}><option value="text">Text</option><option value="file">File</option></select>{item.kind === 'file' ? <label className="file-picker"><input type="file" onChange={event => updateFormData(index, 'file', event.target.files?.[0] || null)} /><span>{item.file?.name || item.filename || '파일 선택'}</span></label> : <input value={item.value} placeholder="value" onChange={event => updateFormData(index, 'value', event.target.value)} />}<button className="icon" onClick={() => removeFormData(index)}>×</button></div>)}<button className="text-button" onClick={() => setForm(current => ({ ...current, formData: [...current.formData, emptyFormDataRow()] }))}>＋ form-data 추가</button><p className="hint">선택한 파일은 저장·재실행할 수 있도록 <code>case/{'{tag}'}/{'{api_name}'}/files/</code>에 보관됩니다. multipart Content-Type은 자동으로 설정됩니다.</p></> : <JsonArea value={form.body} onChange={value => set('body', value)} placeholder={'{\n  "name": "Ada"\n}'} />}</div>}
        </div>
      </section>
      <section className="card">
        <div className="section-header"><div><p className="eyebrow">ASSERTION</p><h2>기대 응답</h2></div></div>
        <div className="validation-method-section"><strong>검증 방법</strong><p className="hint">두 방법 중 하나만 선택하거나 둘 다 선택할 수 있습니다. Expected status는 선택과 관계없이 항상 검증합니다.</p><div className="validation-methods"><label className={`validation-method ${form.validateExact ? 'selected' : ''}`}><input type="checkbox" checked={form.validateExact} onChange={event => set('validateExact', event.target.checked)} /><span><strong>기대 응답 일치</strong><small>Expected body와 실제 응답의 값·구조를 비교합니다.</small></span></label><label className={`validation-method ${form.validateConditions ? 'selected' : ''}`}><input type="checkbox" checked={form.validateConditions} onChange={event => set('validateConditions', event.target.checked)} /><span><strong>변수별 조건</strong><small>선택한 변수의 범위·타입·형식·존재·길이를 검사합니다.</small></span></label></div></div>
        <div className="expected-controls"><Field label="Expected status"><input value={form.expectedStatus} onChange={event => set('expectedStatus', event.target.value)} /></Field><Field label="최대 응답 시간 (ms)"><input type="number" min="0" step="any" value={form.maxResponseTimeMs} onChange={event => set('maxResponseTimeMs', event.target.value)} placeholder="미설정" /></Field>{form.validateExact && <label className="toggle"><input type="checkbox" checked={form.strict} onChange={event => set('strict', event.target.checked)} /><span>strict 비교</span></label>}</div>
        <p className="hint">최대 응답 시간을 설정하면 응답 본문 수신까지 걸린 시간이 기준을 초과할 때 실패합니다. 비우면 시간 검증을 끄며, 측정값은 실행 로그에 표시됩니다. API timeout은 요청 대기 제한입니다.</p>
        {(form.validateExact || form.validateConditions) && <><div className="expected-body-heading"><strong>{form.validateExact ? form.validateConditions ? 'Expected body / 변수 예시 JSON' : 'Expected body' : '변수 예시 JSON'}</strong><span>{form.validateExact ? form.validateConditions ? '일치 검증과 변수 조건 선택에 사용' : '일치 검증에 사용' : '변수 조건 선택에 사용'}</span></div><JsonArea value={form.expectedBody} onChange={value => set('expectedBody', value)} placeholder={'{\n  "id": 1\n}'} /></>}
        {form.validateConditions && <AssertionEditor assertions={form.assertions} variables={responseVariables} enabled onAdd={addAssertion} onUpdate={updateAssertion} onConfirm={confirmAssertion} onSelectVariable={selectAssertionVariable} onRemove={removeAssertion} />}
      </section>
      <div className="case-run-action"><button className="primary" onClick={runOnly}>실행</button></div>
      {notice && <p className="notice">{notice}</p>}<RunResult result={result} onClose={() => setResult(null)} />
    </main>
  </div>
}

export { CaseEditor }
