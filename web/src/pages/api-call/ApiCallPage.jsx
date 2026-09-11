import { Field } from '../../components/Field.jsx'
import { AuthorizationEditor } from '../../components/AuthorizationEditor.jsx'
import { JsonArea } from '../../components/JsonArea.jsx'
import { useState } from 'react'

function ApiCallPage() {
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
    if (!/^https?:\/\//i.test(trimmedUrl)) {
      setErrorNotice('올바른 HTTP 또는 HTTPS 절대 URL을 입력하세요 (예: https://api.example.com).')
      return
    }
    if (trimmedUrl.includes('{{') && trimmedUrl.includes('}}')) {
      setErrorNotice('프로젝트 변수 참조식({{...}})은 일회성 API 호출에서 지원되지 않습니다.')
      return
    }

    setLoading(true)
    setErrorNotice('')
    setResult(null)

    try {
      const payload = {
        method,
        url: trimmedUrl,
        params: params.filter(p => p.key.trim()),
        headers,
        auth: { type: authType, ...authValues },
        body: ['GET', 'HEAD'].includes(method) ? undefined : body,
        proxy_url: proxyUrl.trim(),
        no_proxy: noProxy,
      }
      const response = await fetch('/api/request', {
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
      setErrorNotice(err.message)
    } finally {
      setLoading(false)
    }
  }

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

          {requestTab === 'Authorization' && (
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
            <div>
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

      {errorNotice && (
        <div className="api-call-error-banner" role="alert">
          <strong>요청 오류:</strong> {errorNotice}
        </div>
      )}

      {result && (
        <section className="card api-call-result-panel" role="region" aria-live="polite">
          <div className="api-call-result-header">
            <div className="result-status-group">
              <span className={`status-badge ${statusColorClass(result.status)}`}>
                {result.status}
              </span>
              <span className="elapsed-time">
                ⏱ {result.elapsedMs} ms
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
