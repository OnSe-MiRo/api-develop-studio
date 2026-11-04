import { useState } from 'react'
import { ContractSummary } from './ContractSummary.jsx'
import { asText } from '../utils/studio.js'

function RunResult({ result, onCancel }) {
  const [downloadError, setDownloadError] = useState('')
  if (!result) return null
  const active = ['queued', 'running', 'cancelling', 'reconnecting'].includes(result.status)
  const statusLabels = { not_run: '실행 안 함', reconnecting: '상태 확인 중', queued: '실행 대기 중', running: '실행 중', cancelling: '취소 중', cancelled: '실행 취소됨', timeout: '실행 시간 초과', passed: '실행 완료', failed: '실행 실패', error: '실행 오류' }
  const outputLines = asText(result.output).split('\n')
  const apiCallResults = outputLines.flatMap(line => {
    const value = line.trim().replace(/^actual_response=/, '')
    if (value === line.trim()) return []
    try { return [JSON.stringify(JSON.parse(value), null, 2)] } catch { return [value] }
  })
  const calls = []
  const executionLines = []
  let incomplete = false
  for (const line of outputLines) {
    const value = line.trim()
    if (value.startsWith('call_details=')) {
      try {
        const call = JSON.parse(value.slice('call_details='.length))
        if (!call || typeof call !== 'object' || !call.request) throw new Error('Invalid call details')
        calls.push(call)
      } catch { incomplete = true; executionLines.push(line) }
    } else if (!value.startsWith('actual_response=')) executionLines.push(line)
  }
  const executionLog = executionLines.join('\n')
  const completed = ['passed', 'failed', 'error', 'timeout', 'cancelled'].includes(result.status)
  const download = () => {
    setDownloadError('')
    try {
      const snapshot = { ...result, calls, incomplete: incomplete || asText(result.output).includes('[실행 출력은 1 MiB까지만 표시합니다.]') }
      const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json;charset=utf-8' }))
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `api-result-${(result.runId || 'run').replace(/[^a-zA-Z0-9_-]/g, '_')}.json`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { setDownloadError('결과 파일을 다운로드하지 못했습니다. 다시 시도하세요.') }
  }
  return <section className={`run-result ${active ? 'pending' : result.error || result.exitCode || ['failed', 'timeout', 'cancelled', 'error'].includes(result.status) ? 'failure' : 'success'}`}>
    {completed && <div className="result-heading"><button className="ghost" onClick={download}>실행 결과 JSON 다운로드</button></div>}
    {downloadError && <p role="alert">{downloadError}</p>}
    {incomplete && <p role="alert">호출 정보 일부가 잘렸거나 읽을 수 없습니다. 실행 로그에서 수집된 범위를 확인하세요.</p>}
    {calls.map((call, index) => <div className="card" key={index}>
      <div className="result-heading"><strong>호출 {index + 1} · {call.request.method} {call.response ? `· HTTP ${call.response.status}` : '· 응답 없음'}</strong><span style={{ marginLeft: 12 }}>{typeof call.elapsedMs === 'number' ? `${call.elapsedMs.toFixed(2)} ms` : ''}</span></div>
      <p style={{ overflowWrap: 'anywhere' }}><code>{call.request.url}</code></p>
      {call.mode === 'call_only' && <p className="hint">API 호출만 · 응답 검증 안 함</p>}
      <details><summary>요청 정보 · 헤더 / 본문</summary><pre>{JSON.stringify(call.request, null, 2)}</pre></details>
      {call.response && <><details><summary>응답 헤더</summary><pre>{JSON.stringify(call.response.headers, null, 2)}</pre></details><strong>응답 본문</strong><pre>{typeof call.response.body === 'string' ? call.response.body : JSON.stringify(call.response.body, null, 2)}</pre></>}
      {call.error && <p role="alert">{call.error}</p>}
    </div>)}
    {result.pollError && <p className="notice" role="alert">{result.pollError}</p>}
    {active && onCancel && <button className="danger-button" disabled={result.status === 'cancelling'} onClick={onCancel}>실행 취소</button>}
    {result.historyWarning && <p className="notice" role="alert">{result.historyWarning}</p>}
    {result.runId && <div className="result-heading"><span>Run ID: <code>{result.runId}</code></span></div>}
    <div className="result-heading"><strong>{statusLabels[result.status] || (result.error ? '실행 오류' : result.exitCode ? `실행 실패 (종료 코드 ${result.exitCode})` : '실행 완료')}</strong></div>
    {apiCallResults.length > 0 && <div style={{ padding: '14px', borderTop: '1px solid #dbe4f0', background: '#f8fbff' }}><strong style={{ color: '#334155', fontSize: 13 }}>API 호출 결과</strong><pre style={{ maxHeight: 260, margin: '10px 0 0', border: '1px solid #dbe4f0', borderRadius: 8 }}>{apiCallResults.map((value, index) => `${apiCallResults.length > 1 ? `호출 ${index + 1}\n` : ''}${value}`).join('\n\n')}</pre></div>}
    {result.result?.cleanupStatus && result.result.cleanupStatus !== 'not_run' && <p>본 실행: {statusLabels[result.result.mainStatus] || result.result.mainStatus} · 정리: {statusLabels[result.result.cleanupStatus] || result.result.cleanupStatus}</p>}
    {result.result?.targets?.length > 0 && <div><strong>단계별 결과</strong><ul>{result.result.targets.map((item, index) => <li key={index}>{item.phase === 'teardown' ? '정리 · ' : item.phase === 'setup' ? '준비 · ' : '테스트 · '}{item.caseId} · {statusLabels[item.status] || item.status}{item.httpStatus != null ? ` · HTTP ${item.httpStatus}` : ''}{item.errorCategory ? ` · ${item.errorCategory}` : ''}<ContractSummary contract={item.contract} /></li>)}</ul></div>}
    {(result.error || executionLog) && <div className="result-heading"><strong>실행 로그</strong></div>}
    {(result.error || executionLog) && <pre>{result.error || executionLog}</pre>}
  </section>
}

export { RunResult }
