import { useEffect, useState, useRef, useMemo } from 'react'
import { Field } from '../../components/Field.jsx'
import { api } from '../../utils/studio.js'

export function MockServerPanel({ projectRef, project }) {
  const [data, setData] = useState({
    status: 'stopped',
    host: '127.0.0.1',
    port: 8880,
    url: '',
    seed: 42,
    scenario: 'default',
    defaultLatencyMs: 0,
    activeOperations: 0,
    requestCount: 0,
    overrides: {},
  })
  const [port, setPort] = useState('')
  const [seed, setSeed] = useState(42)
  const [scenario, setScenario] = useState('default')
  const [latency, setLatency] = useState(0)
  const [overrides, setOverrides] = useState({})
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const sequence = useRef(0)

  // Selected operation for override editing
  const [selectedOpKey, setSelectedOpKey] = useState('')
  const [overrideStatus, setOverrideStatus] = useState('')
  const [overrideExampleKey, setOverrideExampleKey] = useState('')
  const [overrideMediaType, setOverrideMediaType] = useState('')
  const [overrideLatency, setOverrideLatency] = useState('')
  const [overrideError, setOverrideError] = useState(false)

  const isRunning = data.status === 'running'

  // ApiList resolves all supported specification sources via /api/docs.
  const operations = useMemo(() => {
    return (project?.mockOperations || []).map(op => ({
      key: op.editable?.operationId || op.id,
      path: op.path,
      method: op.method,
      responses: (op.responses || []).map(response => String(response.status)),
      responseSpecs: Object.fromEntries((op.responses || []).map(response => [String(response.status), {
        mediaTypes: Object.keys(response.mock_content || {}),
        examples: Object.fromEntries(Object.entries(response.mock_content || {}).map(([type, media]) => [type, media.examples || []])),
      }])),
    }))
  }, [project?.mockOperations])

  const selectedOp = useMemo(() => {
    return operations.find(o => o.key === selectedOpKey) || null
  }, [operations, selectedOpKey])

  const availableMediaTypes = useMemo(() => {
    if (!selectedOp) return []
    const status = overrideStatus || selectedOp.responses.find(code => /^2\d\d$/.test(code)) || selectedOp.responses[0]
    return selectedOp.responseSpecs[status]?.mediaTypes || []
  }, [selectedOp, overrideStatus])

  const availableExamples = useMemo(() => {
    if (!selectedOp) return []
    const status = overrideStatus || selectedOp.responses.find(code => /^2\d\d$/.test(code)) || selectedOp.responses[0]
    const media = overrideMediaType || (availableMediaTypes.includes('application/json') ? 'application/json' : availableMediaTypes[0])
    return selectedOp.responseSpecs[status]?.examples[media] || []
  }, [selectedOp, overrideStatus, overrideMediaType, availableMediaTypes])

  const loadStatus = async () => {
    if (!projectRef) return
    const id = ++sequence.current
    setBusy(true)
    setError('')
    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectRef)}/mock`)
      if (sequence.current === id) {
        setData(res)
        setOverrides(res.overrides || {})
        if (res.status === 'running') {
          setPort(res.port || '')
          setSeed(res.seed !== undefined ? res.seed : 42)
          setScenario(res.scenario || 'default')
          setLatency(res.defaultLatencyMs || 0)
        }
      }
    } catch (err) {
      if (sequence.current === id) {
        setError(err.message)
        // Reset to stopped on fetch failure so we don't display a stale running state
        setData(prev => ({ ...prev, status: 'error' }))
      }
    } finally {
      if (sequence.current === id) setBusy(false)
    }
  }

  useEffect(() => {
    setNotice('')
    setError('')
    loadStatus()
    return () => { ++sequence.current }
  }, [projectRef, project?._storage?.revision])

  const startServer = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const payload = {
        seed: Number(seed),
        scenario,
        defaultLatencyMs: Number(latency),
        overrides,
      }
      if (port) payload.port = Number(port)
      const res = await api(`/api/projects/${encodeURIComponent(projectRef)}/mock/start`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setData(res)
      setOverrides(res.overrides || {})
      setPort(res.port || '')
      setNotice(`Mock Server가 실행되었습니다: ${res.url}`)
    } catch (err) {
      setError(`Mock Server 시작 실패: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  const stopServer = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api(`/api/projects/${encodeURIComponent(projectRef)}/mock/stop`, {
        method: 'POST',
      })
      await loadStatus()
      setNotice('Mock Server가 중지되었습니다.')
    } catch (err) {
      setError(`Mock Server 중지 실패: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  const resetServer = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api(`/api/projects/${encodeURIComponent(projectRef)}/mock/reset`, {
        method: 'POST',
      })
      await loadStatus()
      setNotice('Mock Server State가 초기화되었습니다.')
    } catch (err) {
      setError(`State 초기화 실패: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  const applyConfig = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectRef)}/mock/config`, {
        method: 'POST',
        body: JSON.stringify({
          seed: Number(seed),
          scenario,
          defaultLatencyMs: Number(latency),
          overrides,
        }),
      })
      setData(res)
      setOverrides(res.overrides || {})
      setNotice('Mock Server 설정이 적용되었습니다.')
    } catch (err) {
      setError(`설정 적용 실패: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  const addOrUpdateOverride = () => {
    if (!selectedOpKey) return
    const newOv = {}
    if (overrideStatus) newOv.status = Number(overrideStatus)
    if (overrideExampleKey && availableExamples.includes(overrideExampleKey)) newOv.exampleKey = overrideExampleKey
    if (overrideMediaType && availableMediaTypes.includes(overrideMediaType)) newOv.mediaType = overrideMediaType
    if (overrideLatency !== '') newOv.latencyMs = Number(overrideLatency)
    if (overrideError) newOv.errorResponse = true

    setOverrides(prev => ({
      ...prev,
      [selectedOpKey]: newOv,
    }))
    setNotice(`Operation '${selectedOpKey}' 오버라이드가 등록되었습니다. (설정 적용 버튼을 눌러 서버에 반영하세요)`)
  }

  const removeOverride = (key) => {
    setOverrides(prev => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  return (
    <section className="card" aria-label="OpenAPI Mock Server">
      <div className="section-header">
        <div>
          <h2>
            OpenAPI Mock Server
            <span
              style={{
                marginLeft: 10,
                padding: '3px 8px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                color: isRunning ? '#15803d' : '#64748b',
                background: isRunning ? '#dcfce7' : '#f1f5f9',
              }}
            >
              {isRunning ? '실행 중' : data.status === 'error' ? '상태 확인 실패' : '중지됨'}
            </span>
          </h2>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {!isRunning ? (
            <button
              className="primary"
              disabled={!projectRef || busy}
              onClick={startServer}
            >
              {busy ? '처리 중…' : '서버 시작'}
            </button>
          ) : (
            <>
              <button
                className="danger"
                disabled={busy}
                onClick={stopServer}
                style={{ color: '#b91c1c', borderColor: '#fca5a5' }}
              >
                중지
              </button>
              <button
                className="ghost"
                disabled={busy}
                onClick={resetServer}
              >
                State 초기화
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={applyConfig}
              >
                설정 적용
              </button>
            </>
          )}
          <button
            className="ghost"
            disabled={!projectRef || busy}
            onClick={loadStatus}
          >
            새로고침
          </button>
        </div>
      </div>

      <div className="hint" style={{ fontSize: 13, lineHeight: 1.6, marginBottom: 16 }}>
        <p style={{ margin: '0 0 6px 0' }}>
          <strong>운영 안내:</strong>
        </p>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          <li><strong>단일 프로세스 인메모리 실행:</strong> Mock Server는 Studio 내부 백그라운드 이벤트 루프에서 실행되며, 서버 중지 또는 Studio 재시작 시 CRUD State는 소멸됩니다.</li>
          <li><strong>명세 스냅샷 정책:</strong> 서버 시작 시점의 OpenAPI 명세를 기준으로 동작합니다. 명세 변경 후에는 Mock Server를 재시작해야 최신 명세가 반영됩니다.</li>
          <li>Seed 또는 시나리오 값을 변경하면 State가 초기화됩니다. 지연·응답 설정만 변경하면 유지됩니다.</li>
          <li>Example 또는 미디어 타입을 직접 선택하면 명세 응답을 재생하며 CRUD State를 변경하지 않습니다.</li>
          <li><strong>Loopback 전용 바인드:</strong> 127.0.0.1, ::1 등 로컬 루프백 주소로만 안전하게 바인드됩니다.</li>
        </ul>
      </div>

      {isRunning && (
        <div
          role="status"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 12,
            padding: 14,
            marginBottom: 16,
            borderRadius: 8,
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
          }}
        >
          <div>
            <small style={{ color: '#64748b', display: 'block' }}>접속 URL</small>
            <code style={{ fontSize: 13, color: '#2563eb', fontWeight: 600 }}>{data.url}</code>
          </div>
          <div>
            <small style={{ color: '#64748b', display: 'block' }}>바인드 호스트 / 포트</small>
            <code>{data.host}:{data.port}</code>
          </div>
          <div>
            <small style={{ color: '#64748b', display: 'block' }}>활성 Operation 수</small>
            <strong>{data.activeOperations}개</strong>
          </div>
          <div>
            <small style={{ color: '#64748b', display: 'block' }}>누적 처리 요청</small>
            <strong>{data.requestCount}회</strong>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        <Field label="포트 (비워두면 자동 할당)">
          <input
            type="number"
            disabled={isRunning || busy}
            value={port}
            onChange={e => setPort(e.target.value)}
            placeholder="8880"
          />
        </Field>

        <Field label="고정 Seed">
          <input
            type="number"
            disabled={busy}
            value={seed}
            onChange={e => setSeed(e.target.value)}
          />
        </Field>

        <Field label="시나리오">
          <select
            disabled={busy}
            value={scenario}
            onChange={e => setScenario(e.target.value)}
          >
            <option value="default">기본 (선언형 CRUD State)</option>
            <option value="error_simulation">오류 시뮬레이션 (500 오류 반환)</option>
            <option value="not_found">404 시뮬레이션 (Not Found 반환)</option>
          </select>
        </Field>

        <Field label="기본 응답 지연 (ms, 최대 5000)">
          <input
            type="number"
            min="0"
            max="5000"
            disabled={busy}
            value={latency}
            onChange={e => setLatency(e.target.value)}
          />
        </Field>
      </div>

      {/* Per-operation Overrides Configuration */}
      <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #e2e8f0' }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Operation별 오버라이드 설정 (Overrides)</h3>
        <p className="hint" style={{ marginBottom: 12 }}>
          개별 Operation에 대해 반환할 응답 상태 코드, 특정 Example, 미디어 타입, 응답 지연 시간 또는 오류 시뮬레이션을 설정합니다.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, alignItems: 'flex-end' }}>
          <Field label="대상 Operation">
            <select
              value={selectedOpKey}
              onChange={e => {
                const key = e.target.value
                setSelectedOpKey(key)
                const existing = overrides[key] || {}
                setOverrideStatus(existing.status !== undefined ? String(existing.status) : '')
                setOverrideExampleKey(existing.exampleKey || '')
                setOverrideMediaType(existing.mediaType || '')
                setOverrideLatency(existing.latencyMs !== undefined ? String(existing.latencyMs) : '')
                setOverrideError(Boolean(existing.errorResponse))
              }}
            >
              <option value="">-- Operation 선택 --</option>
              {operations.map(op => (
                <option key={op.key} value={op.key}>
                  [{op.method}] {op.path}
                </option>
              ))}
            </select>
          </Field>

          <Field label="상태 코드 (Status)">
            <select
              value={overrideStatus}
              onChange={e => {
                setOverrideStatus(e.target.value)
                setOverrideMediaType('')
                setOverrideExampleKey('')
              }}
              disabled={!selectedOpKey}
            >
              <option value="">-- 기본값 (명세 우선순위) --</option>
              {[...new Set([...(selectedOp?.responses || []).filter(code => /^\d{3}$/.test(code)), '400', '404', '500', '503'])].map(code => (
                <option key={code} value={code}>{code}</option>
              ))}
            </select>
          </Field>

          <Field label="미디어 타입 (Media Type)">
            <select
              value={overrideMediaType}
              onChange={e => {
                setOverrideMediaType(e.target.value)
                setOverrideExampleKey('')
              }}
              disabled={!selectedOpKey}
            >
              <option value="">-- 기본값 --</option>
              {availableMediaTypes.map(mt => (
                <option key={mt} value={mt}>{mt}</option>
              ))}
            </select>
          </Field>

          <Field label="Example 이름">
            <select
              value={overrideExampleKey}
              onChange={e => setOverrideExampleKey(e.target.value)}
              disabled={!selectedOpKey}
            >
              <option value="">-- 기본 Example --</option>
              {availableExamples.map(ex => (
                <option key={ex} value={ex}>{ex}</option>
              ))}
            </select>
          </Field>

          <Field label="지연 시간 (ms)">
            <input
              type="number"
              min="0"
              max="5000"
              placeholder="0"
              value={overrideLatency}
              onChange={e => setOverrideLatency(e.target.value)}
              disabled={!selectedOpKey}
            />
          </Field>

          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={overrideError}
                onChange={e => setOverrideError(e.target.checked)}
                disabled={!selectedOpKey}
              />
              오류 시뮬레이션
            </label>
            <button
              type="button"
              className="secondary"
              disabled={!selectedOpKey || busy}
              onClick={addOrUpdateOverride}
              style={{ width: '100%' }}
            >
              오버라이드 적용
            </button>
          </div>
        </div>

        {/* Active Overrides Table */}
        {Object.keys(overrides).length > 0 && (
          <div style={{ marginTop: 14 }}>
            <small style={{ fontWeight: 600, color: '#475569', display: 'block', marginBottom: 6 }}>
              설정된 오버라이드 목록 ({Object.keys(overrides).length}개)
            </small>
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', textAlign: 'left' }}>
                  <th style={{ padding: '6px 8px' }}>Operation</th>
                  <th style={{ padding: '6px 8px' }}>상태 코드</th>
                  <th style={{ padding: '6px 8px' }}>미디어 타입</th>
                  <th style={{ padding: '6px 8px' }}>Example</th>
                  <th style={{ padding: '6px 8px' }}>지연</th>
                  <th style={{ padding: '6px 8px' }}>오류</th>
                  <th style={{ padding: '6px 8px', textAlign: 'right' }}>관리</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(overrides).map(([key, ov]) => (
                  <tr key={key} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '6px 8px' }}><code>{key}</code></td>
                    <td style={{ padding: '6px 8px' }}>{ov.status || '기본'}</td>
                    <td style={{ padding: '6px 8px' }}>{ov.mediaType || '기본'}</td>
                    <td style={{ padding: '6px 8px' }}>{ov.exampleKey || '-'}</td>
                    <td style={{ padding: '6px 8px' }}>{ov.latencyMs !== undefined ? `${ov.latencyMs}ms` : '-'}</td>
                    <td style={{ padding: '6px 8px' }}>{ov.errorResponse ? '예' : '아니오'}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'right' }}>
                      <button
                        type="button"
                        className="ghost"
                        style={{ padding: '2px 6px', fontSize: 12, color: '#b91c1c' }}
                        onClick={() => removeOverride(key)}
                      >
                        삭제
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {notice && <p role="status" className="notice" style={{ marginTop: 12 }}>{notice}</p>}
      {error && (
        <p
          role="alert"
          className="notice"
          style={{ marginTop: 12, color: '#b91c1c', background: '#fef2f2', borderColor: '#fecaca' }}
        >
          {error}
        </p>
      )}
    </section>
  )
}
