import { Field } from '../../components/Field.jsx'
import { JsonArea } from '../../components/JsonArea.jsx'
import { AuthorSidebar } from '../../components/ProjectSidebar.jsx'
import { commonErrorOptions, operationIdFrom, api, parseJson } from '../../utils/studio.js'
import { useState } from 'react'

const emptyAuthoredParameter = () => ({ name: '', in: 'query', type: 'string', required: false, example: '' })

const emptyAuthoredHeader = () => ({ name: '', type: 'string', required: false, example: '' })

function ApiAuthorEditor({ projects, projectRef, project, refresh, onProjectChange, onNavigate, onProjectList, onSaved }) {
  const [method, setMethod] = useState('GET')
  const [path, setPath] = useState('/v1/resource')
  const [operationId, setOperationId] = useState('getV1Resource')
  const [summary, setSummary] = useState('')
  const [tag, setTag] = useState('default')
  const [parameters, setParameters] = useState([])
  const [headers, setHeaders] = useState([])
  const [errorStatuses, setErrorStatuses] = useState([])
  const [requestBody, setRequestBody] = useState('')
  const [requestRequired, setRequestRequired] = useState(false)
  const [responseStatus, setResponseStatus] = useState('200')
  const [responseDescription, setResponseDescription] = useState('Success')
  const [responseBody, setResponseBody] = useState('')
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const updateMethod = value => { setMethod(value); setOperationId(operationIdFrom(value, path)) }
  const updatePath = value => { setPath(value); setOperationId(operationIdFrom(method, value)) }
  const updateParameter = (index, key, value) => setParameters(current => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  const updateHeader = (index, key, value) => setHeaders(current => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  const parameterPayload = item => {
    let example = item.example
    if (example !== '') {
      if (item.type === 'integer' || item.type === 'number') { example = Number(example); if (!Number.isFinite(example) || (item.type === 'integer' && !Number.isInteger(example))) throw new Error(`${item.name || '파라미터'} 예시값의 타입이 올바르지 않습니다.`) }
      if (item.type === 'boolean') { if (!['true', 'false'].includes(String(example).toLowerCase())) throw new Error(`${item.name || '파라미터'} 예시값은 true 또는 false여야 합니다.`); example = String(example).toLowerCase() === 'true' }
    }
    return { name: item.name, in: item.in, type: item.type, required: item.required, example }
  }
  const save = async () => {
    setSaving(true)
    try {
      if (!projectRef || !project?._storage) throw new Error('작성할 프로젝트를 선택하세요.')
      const payload = {
        method, path, operation_id: operationId, summary, tag,
        parameters: [
          ...parameters.filter(item => item.name.trim()).map(parameterPayload),
          ...headers.filter(item => item.name.trim()).map(item => parameterPayload({ ...item, in: 'header' })),
        ],
        has_request_body: Boolean(requestBody.trim()), request_body_required: requestRequired,
        response_status: Number(responseStatus), response_description: responseDescription,
        has_response_body: Boolean(responseBody.trim()), _storage: project._storage,
        error_statuses: errorStatuses,
      }
      if (payload.has_request_body) payload.request_body = parseJson(requestBody, 'Request body', true)
      if (payload.has_response_body) payload.response_body = parseJson(responseBody, 'Response body', true)
      await api(`/api/projects/${encodeURIComponent(projectRef)}/openapi/operations`, { method: 'POST', body: JSON.stringify(payload) })
      await refresh(projectRef); onSaved()
    } catch (error) { setNotice(error.message) }
    finally { setSaving(false) }
  }
  return <div className="workspace">
    <AuthorSidebar active="apis" projects={projects} projectRef={projectRef} project={project} onProjectChange={onProjectChange} onNavigate={onNavigate} onProjectList={onProjectList} />
    <main className="editor">
      <section className="card"><div className="section-header"><div><p className="eyebrow">NEW OPENAPI OPERATION</p><h2>API 작성</h2></div><div className="actions"><button className="ghost" onClick={onSaved}>목록으로</button><button className="primary" disabled={saving} onClick={save}>{saving ? '저장 중…' : 'API 저장'}</button></div></div>{project?.docs_url && <p className="authoring-copy-notice">저장하면 URL 문서를 현재 프로젝트의 편집 가능한 OpenAPI 사본으로 전환합니다. 원격 문서는 변경하지 않습니다.</p>}<div className="api-author-grid"><Field label="Method"><select value={method} onChange={event => updateMethod(event.target.value)}>{['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(value => <option key={value}>{value}</option>)}</select></Field><Field label="Path" wide><input value={path} onChange={event => updatePath(event.target.value)} placeholder="/v1/users/{userId}" /></Field><Field label="Operation ID"><input value={operationId} onChange={event => setOperationId(event.target.value)} /></Field><Field label="Tag"><input value={tag} onChange={event => setTag(event.target.value)} /></Field><Field label="Summary" wide><input value={summary} onChange={event => setSummary(event.target.value)} placeholder="API 설명" /></Field></div></section>
      <section className="card"><div className="section-header"><div><p className="eyebrow">PARAMETERS</p><h2>Path / Query 파라미터</h2></div><button className="ghost" onClick={() => setParameters(current => [...current, emptyAuthoredParameter()])}>＋ 파라미터 추가</button></div>{parameters.length ? <div className="api-author-parameters">{parameters.map((item, index) => <div className="api-author-parameter" key={index}><input aria-label={`${index + 1}번째 파라미터 이름`} value={item.name} onChange={event => updateParameter(index, 'name', event.target.value)} placeholder="name" /><select aria-label={`${index + 1}번째 파라미터 위치`} value={item.in} onChange={event => updateParameter(index, 'in', event.target.value)}>{['path', 'query'].map(value => <option key={value}>{value}</option>)}</select><select aria-label={`${index + 1}번째 파라미터 타입`} value={item.type} onChange={event => updateParameter(index, 'type', event.target.value)}>{['string', 'integer', 'number', 'boolean'].map(value => <option key={value}>{value}</option>)}</select><input aria-label={`${index + 1}번째 파라미터 예시`} value={item.example} onChange={event => updateParameter(index, 'example', event.target.value)} placeholder="예시값" /><label className="toggle"><input type="checkbox" checked={item.required || item.in === 'path'} disabled={item.in === 'path'} onChange={event => updateParameter(index, 'required', event.target.checked)} /><span>필수</span></label><button className="icon danger" aria-label={`${index + 1}번째 파라미터 삭제`} onClick={() => setParameters(current => current.filter((_, itemIndex) => itemIndex !== index))}>×</button></div>)}</div> : <div className="empty compact">파라미터가 없습니다. Path의 {'{변수}'}는 저장 시 자동으로 path 파라미터가 됩니다.</div>}</section>
      <section className="card"><div className="section-header"><div><p className="eyebrow">REQUEST HEADERS</p><h2>Headers</h2></div><button className="ghost" onClick={() => setHeaders(current => [...current, emptyAuthoredHeader()])}>＋ Header 추가</button></div>{headers.length ? <div className="api-author-headers">{headers.map((item, index) => <div className="api-author-header" key={index}><input aria-label={`${index + 1}번째 Header 이름`} value={item.name} onChange={event => updateHeader(index, 'name', event.target.value)} placeholder="X-Request-Id" /><select aria-label={`${index + 1}번째 Header 타입`} value={item.type} onChange={event => updateHeader(index, 'type', event.target.value)}>{['string', 'integer', 'number', 'boolean'].map(value => <option key={value}>{value}</option>)}</select><input aria-label={`${index + 1}번째 Header 예시`} value={item.example} onChange={event => updateHeader(index, 'example', event.target.value)} placeholder="예시값" /><label className="toggle"><input type="checkbox" checked={item.required} onChange={event => updateHeader(index, 'required', event.target.checked)} /><span>필수</span></label><button className="icon danger" aria-label={`${index + 1}번째 Header 삭제`} onClick={() => setHeaders(current => current.filter((_, itemIndex) => itemIndex !== index))}>×</button></div>)}</div> : <div className="empty compact">등록된 요청 Header가 없습니다.</div>}</section>
      <section className="card"><div className="section-header"><div><p className="eyebrow">COMMON ERROR RESPONSES</p><h2>공통 오류 응답</h2></div></div><p className="hint">선택한 오류는 <code>components/error.yaml</code>의 공통 Response를 참조합니다.</p><div className="common-error-options">{commonErrorOptions.map(([status, label]) => <label key={status}><input type="checkbox" checked={errorStatuses.includes(status)} onChange={event => setErrorStatuses(current => event.target.checked ? [...current, status] : current.filter(value => value !== status))} /><strong>{status}</strong><span>{label}</span></label>)}</div></section>
      <section className="card"><div className="form-grid project-settings-grid"><Field label="Request body JSON" wide><JsonArea value={requestBody} onChange={setRequestBody} placeholder={'{\n  "name": "Ada"\n}'} /></Field><label className="toggle"><input type="checkbox" checked={requestRequired} disabled={!requestBody.trim()} onChange={event => setRequestRequired(event.target.checked)} /><span>Request body 필수</span></label><Field label="응답 상태 코드"><input type="number" min="100" max="599" value={responseStatus} onChange={event => setResponseStatus(event.target.value)} /></Field><Field label="응답 설명"><input value={responseDescription} onChange={event => setResponseDescription(event.target.value)} /></Field><Field label="Response body JSON" wide><JsonArea value={responseBody} onChange={setResponseBody} placeholder={'{\n  "id": 1,\n  "name": "Ada"\n}'} /></Field></div></section>
      {notice && <p className="notice" role="status">{notice}</p>}
    </main>
  </div>
}

export { ApiAuthorEditor }
