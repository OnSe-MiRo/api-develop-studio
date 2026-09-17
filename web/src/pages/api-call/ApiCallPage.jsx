import { Field } from '../../components/Field.jsx'
import { AuthorizationEditor } from '../../components/AuthorizationEditor.jsx'
import { JsonArea } from '../../components/JsonArea.jsx'
import { quickRequest, requestCurl } from './request.js'
import { useEffect, useState, useRef } from 'react'
import { api } from '../../utils/studio.js'

function ApiCallPage() {
  const controller = useRef(null)
  const [environment, setEnvironment] = useState('')
  const [projectDocument, setProjectDocument] = useState({})
  const [authProfile, setAuthProfile] = useState('')
  const [bodyMode, setBodyMode] = useState('json')
  const [casePath, setCasePath] = useState('')
  const [saveNotice, setSaveNotice] = useState('')
  const [project, setProject] = useState('')
  const [validateContract, setValidateContract] = useState(false)
  const [projects, setProjects] = useState([])
  useEffect(() => { api('/api/projects').then(data => setProjects(data.items || [])).catch(error => setErrorNotice(error.message)) }, [])
  useEffect(() => {
    let active = true
    setEnvironment(''); setAuthProfile(''); setProjectDocument({})
    if (project) api(`/api/projects/${encodeURIComponent(project)}`).then(data => { if (active) setProjectDocument(data) }).catch(error => setErrorNotice(error.message))
    return () => { active = false }
  }, [project])
  useEffect(() => () => controller.current?.abort(), [])
  const [method, setMethod] = useState('GET')
  const [url, setUrl] = useState('')
  const [params, setParams] = useState([{ key: '', value: '' }])
  const [authType, setAuthType] = useState('No Auth')
  const [authValues, setAuthValues] = useState({})
  const [headers, setHeaders] = useState('')
  const [body, setBody] = useState('')
  const [proxyUrl, setProxyUrl] = useState('')
  const [noProxy, setNoProxy] = useState(false)
  const [requestTab, setRequestTab] = useState('Params')

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [errorNotice, setErrorNotice] = useState('')
  const [copied, setCopied] = useState(false)
  const [headersExpanded, setHeadersExpanded] = useState(false)

  const updateParam = (index, field, value) => {
    setParams(current => current.map((item, idx) => idx === index ? { ...item, [field]: value } : item))
  }
  const removeParam = index => {
    setParams(current => current.filter((_, idx) => idx !== index))
  }
  const addParam = () => {
    setParams(current => [...current, { key: '', value: '' }])
  }

  const handleRun = async () => {
    const trimmedUrl = url.trim()
    if (!trimmedUrl) {
      setErrorNotice('URL을 입력하세요.')
      return
    }
    setLoading(true)
    setErrorNotice('')
    setResult(null)

    try {
      const payload = { project, environment, validateContract, body_format: bodyMode, ...makeRequest(), proxy_url: proxyUrl.trim(), no_proxy: noProxy }
      controller.current = new AbortController()
      const response = await fetch('/api/request', {
        signal: controller.current.signal,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.error || '요청 처리에 실패했습니다.')
      }
      setResult(data)
    } catch (err) {
      setErrorNotice(err.name === 'AbortError' ? '응답 대기를 취소했습니다. 서버의 전송은 완료될 수 있습니다.' : err.message)
    } finally {
      setLoading(false)
    }
  }

  const makeRequest = () => quickRequest({ method, url, params, headers, body, bodyMode, authType, authValues, authProfile })
  const saveCase = async () => {
    try {
      const request = makeRequest()
      if (!project) throw new Error('프로젝트를 선택하세요.')
      if (!/^[^/]+\/[^/]+\/[^/]+\.json$/.test(casePath)) throw new Error('tag/api_name/case_file.json 형식으로 입력하세요.')
      if (!authProfile && authType !== 'No Auth') throw new Error('인증값을 저장하려면 프로젝트의 인증 프로필을 선택하세요.')
      if (Object.entries(request.headers).some(([key, value]) => /authorization|cookie|token|key/i.test(key) && !/^\{\{project\.[^}]+\}\}$/.test(value))) throw new Error('민감 헤더는 암호화 프로젝트 변수 참조로 변경하세요.')
      const existing = await api('/api/cases')
      if (existing.items.includes(casePath)) throw new Error('이미 존재하는 케이스 경로입니다.')
      await api(`/api/cases/${encodeURIComponent(casePath)}`, { method: 'PUT', body: JSON.stringify({ name: casePath.split('/').pop().replace('.json', ''), project, request, expected: { status: result?.status || 200 } }) })
      setSaveNotice(`케이스 저장 완료: ${casePath}`)
    } catch (error) { setErrorNotice(error.message) }
  }
  const copyCurl = async () => {
    try {
      const request = makeRequest()
      if (!/^https?:\/\//i.test(request.url)) {
        const base = projectDocument.environments?.[environment || projectDocument.default_environment]?.base_url || projectDocument.base_url
        if (!base) throw new Error('절대 URL 또는 프로젝트를 선택하세요.')
        request.url = `${base.replace(/\/$/, '')}/${request.url.replace(/^\//, '')}`
      }
      await navigator.clipboard.writeText(requestCurl(request)); setSaveNotice('민감 필드가 마스킹된 cURL을 복사했습니다. 인증 프로필과 변수 참조는 실행 전에 직접 설정하세요.')
    }
    catch (error) { setErrorNotice(error.message) }
  }
  const profiles = { ...projectDocument.auth_profiles, ...projectDocument.environments?.[environment || projectDocument.default_environment]?.auth_profiles }

  const copyResponseBody = () => {
    if (!result) return
    const text = typeof result.body === 'object' && result.body !== null
      ? JSON.stringify(result.body, null, 2)
      : (result.rawBody || '')
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const statusColorClass = status => {
    if (status >= 200 && status < 300) return 'status-2xx'
    if (status >= 300 && status < 400) return 'status-3xx'
    if (status >= 400 && status < 500) return 'status-4xx'
    return 'status-5xx'
  }

  return (
    <main className="project-page api-call-page">
      <section className="card"><Field label="소유권 확인 프로젝트"><select value={project} onChange={event => { setProject(event.target.value); setValidateContract(false) }}><option value="">프로젝트 선택 (로컬 인증 생략 시 선택사항)</option>{projects.map(item => <option key={item}>{item}</option>)}</select></Field><Field label="실행 환경"><select value={environment} onChange={event => setEnvironment(event.target.value)}><option value="">프로젝트 기본 환경</option>{Object.keys(projectDocument.environments || {}).map(name => <option key={name}>{name}</option>)}</select></Field><Field label="공통 인증 프로필"><select value={authProfile} onChange={event => setAuthProfile(event.target.value)}><option value="">직접 설정</option>{Object.keys(profiles).map(name => <option key={name}>{name}</option>)}</select></Field><label className="toggle"><input type="checkbox" checked={validateContract} disabled={!project} onChange={event => setValidateContract(event.target.checked)} />OpenAPI 실제 응답 검증</label><p className="hint">프로젝트 설정에서 대상 Base URL을 저장하고 소유권을 확인하세요.</p></section>
      <section className="card">
        <div className="section-header">
          <div>
            <p className="eyebrow">QUICK HTTP REQUEST</p>
            <h2>API 호출</h2>
          </div>
        </div>
        <div className="request-bar api-call-request-bar">
          <select
            className="method"
            value={method}
            onChange={e => setMethod(e.target.value)}
            aria-label="HTTP Method"
          >
            {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <input
            className="url-input"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://api.example.com/v1/users (절대 HTTP/HTTPS URL)"
            aria-label="Request URL"
            onKeyDown={e => { if (e.key === 'Enter' && !loading) handleRun() }}
          />
          <button
            className="primary run-button"
            onClick={handleRun}
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? '호출 중...' : '실행'}
          </button>
        </div>

        <div className="actions"><button disabled={!loading} onClick={() => controller.current?.abort()}>응답 대기 취소</button><button onClick={copyCurl}>cURL 복사 (마스킹)</button></div>
        <div className="tabs">
          {['Params', 'Authorization', 'Headers', 'Body', 'Proxy'].map(tab => (
            <button
              key={tab}
              className={requestTab === tab ? 'active' : ''}
              onClick={() => setRequestTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="tab-content" style={requestTab === 'Params' ? { minHeight: 0, paddingBottom: 14 } : undefined}>
          {requestTab === 'Params' && (
            <>
              <div className="param-header">
                <span>Key</span>
                <span>Value</span>
                <span />
              </div>
              {params.map((param, index) => (
                <div className="param-row" key={index}>
                  <input
                    value={param.key}
                    placeholder="key"
                    aria-label={`Param Key ${index + 1}`}
                    onChange={e => updateParam(index, 'key', e.target.value)}
                  />
                  <input
                    value={param.value}
                    placeholder="value"
                    aria-label={`Param Value ${index + 1}`}
                    onChange={e => updateParam(index, 'value', e.target.value)}
                  />
                  <button
                    className="icon"
                    aria-label={`Parameter ${index + 1} 삭제`}
                    onClick={() => removeParam(index)}
                  >
                    ×
                  </button>
                </div>
              ))}
              <button className="text-button" onClick={addParam}>
                ＋ Parameter 추가
              </button>
            </>
          )}

          {requestTab === 'Authorization' && !authProfile && (
            <AuthorizationEditor type={authType} values={authValues} onTypeChange={value => { setAuthType(value); setAuthValues({}) }} onValueChange={(key, value) => setAuthValues(current => ({ ...current, [key]: value }))} />
          )}

          {requestTab === 'Headers' && (
            <JsonArea
              value={headers}
              onChange={setHeaders}
              placeholder={'Content-Type: application/json\nX-Custom-Header: value'}
            />
          )}

          {requestTab === 'Body' && (
            <div><Field label="본문 형식"><select value={bodyMode} onChange={event => setBodyMode(event.target.value)}><option value="json">JSON</option><option value="text">Text</option><option value="form-data">Form Data</option></select></Field>{bodyMode === 'form-data' && <p className="hint">{'[{"key":"name","value":"example"}] 형식. 파일은 case/ 기준 file 경로로 지정합니다.'}</p>}
              <JsonArea
                value={body}
                onChange={setBody}
                placeholder={'{\n  "name": "example"\n}'}
              />
            </div>
          )}

          {requestTab === 'Proxy' && (
            <section className="quick-proxy-settings">
              <label className="toggle"><input type="checkbox" checked={noProxy} onChange={event => setNoProxy(event.target.checked)} /><span>프록시 사용 안 함 (No Proxy)</span></label>
              <Field label="Proxy URL (HTTP/HTTPS)"><input disabled={noProxy} value={proxyUrl} onChange={event => setProxyUrl(event.target.value)} placeholder="http://proxy.example.com:8080" /></Field>
              <p className="hint">프록시 URL을 입력하면 이번 API 호출에만 적용합니다. No Proxy를 선택하면 설정된 주소와 환경 프록시를 모두 우회합니다.</p>
            </section>
          )}
        </div>
      </section>

      <section className="card"><Field label="새 케이스 경로"><input value={casePath} onChange={event => setCasePath(event.target.value)} placeholder="tag/api_name/case_file.json" /></Field><button onClick={saveCase}>현재 요청을 새 케이스로 저장</button>{saveNotice && <p role="status">{saveNotice}</p>}</section>
      {errorNotice && (
        <div className="api-call-error-banner" role="alert">
          <strong>요청 오류:</strong> {errorNotice}
        </div>
      )}

      {result && (
        <section className="card api-call-result-panel" role="region" aria-live="polite">
          {result.contract && <div role="status"><h3>{result.contract.valid ? '응답 계약 검증 통과' : '응답 계약 검증 실패'}</h3>{result.contract.issues.map((item, index) => <p key={index}>{item.code} · <code>{item.path}</code></p>)}</div>}
          <div className="api-call-result-header">
            <div className="result-status-group">
              <span className={`status-badge ${statusColorClass(result.status)}`}>
                {result.status}
              </span>
              <span className="elapsed-time">
                ⏱ {result.elapsedMs} ms · {result.sizeBytes} bytes
              </span>
            </div>
            <div className="result-actions">
              <button className="ghost small" onClick={copyResponseBody}>
                {copied ? '복사됨!' : '본문 복사'}
              </button>
            </div>
          </div>

          {result.headers && Object.keys(result.headers).length > 0 && (
            <div className="result-headers-section">
              <button
                className="result-headers-toggle"
                onClick={() => setHeadersExpanded(c => !c)}
                aria-expanded={headersExpanded}
              >
                <span>응답 헤더 ({Object.keys(result.headers).length}개)</span>
                <span>{headersExpanded ? '−' : '+'}</span>
              </button>
              {headersExpanded && (
                <div className="result-headers-list">
                  {Object.entries(result.headers).map(([k, v]) => (
                    <div key={k} className="header-entry">
                      <code>{k}:</code> <span>{v}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="result-body-section">
            <div className="result-body-label">응답 본문</div>
            <pre className="result-body-content">
              {typeof result.body === 'object' && result.body !== null
                ? JSON.stringify(result.body, null, 2)
                : (result.rawBody || '(본문 없음)')}
            </pre>
          </div>
        </section>
      )}
    </main>
  )
}

export { ApiCallPage }
