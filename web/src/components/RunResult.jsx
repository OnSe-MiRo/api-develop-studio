import { asText } from '../utils/studio.js'

function RunResult({ result, onCancel }) {
  if (!result) return null
  const active = ['queued', 'running', 'cancelling', 'reconnecting'].includes(result.status)
  const statusLabels = { not_run: '실행 안 함', reconnecting: '상태 확인 중', queued: '실행 대기 중', running: '실행 중', cancelling: '취소 중', cancelled: '실행 취소됨', timeout: '실행 시간 초과', passed: '실행 완료', failed: '실행 실패', error: '실행 오류' }
  const outputLines = asText(result.output).split('\n')
  const apiCallResults = outputLines.flatMap(line => {
    const value = line.trim().replace(/^actual_response=/, '')
    if (value === line.trim()) return []
    try { return [JSON.stringify(JSON.parse(value), null, 2)] } catch { return [value] }
  })
  const executionLog = outputLines.filter(line => !line.trim().startsWith('actual_response=')).join('\n')
  return <section className={`run-result ${active ? 'pending' : result.error || result.exitCode || ['timeout', 'cancelled', 'error'].includes(result.status) ? 'failure' : 'success'}`}>
    {result.pollError && <p className="notice" role="alert">{result.pollError}</p>}
    {active && onCancel && <button className="danger-button" disabled={result.status === 'cancelling'} onClick={onCancel}>실행 취소</button>}
    {result.historyWarning && <p className="notice" role="alert">{result.historyWarning}</p>}
    {result.runId && <div className="result-heading"><span>Run ID: <code>{result.runId}</code></span></div>}
    <div className="result-heading"><strong>{statusLabels[result.status] || (result.error ? '실행 오류' : result.exitCode ? `실행 실패 (종료 코드 ${result.exitCode})` : '실행 완료')}</strong></div>
    {apiCallResults.length > 0 && <div style={{ padding: '14px', borderTop: '1px solid #dbe4f0', background: '#f8fbff' }}><strong style={{ color: '#334155', fontSize: 13 }}>API 호출 결과</strong><pre style={{ maxHeight: 260, margin: '10px 0 0', border: '1px solid #dbe4f0', borderRadius: 8 }}>{apiCallResults.map((value, index) => `${apiCallResults.length > 1 ? `호출 ${index + 1}\n` : ''}${value}`).join('\n\n')}</pre></div>}
    {result.result?.cleanupStatus && result.result.cleanupStatus !== 'not_run' && <p>본 실행: {statusLabels[result.result.mainStatus] || result.result.mainStatus} · 정리: {statusLabels[result.result.cleanupStatus] || result.result.cleanupStatus}</p>}
    {result.result?.targets?.length > 0 && <div><strong>단계별 결과</strong><ul>{result.result.targets.map((item, index) => <li key={index}>{item.phase === 'teardown' ? '정리 · ' : item.phase === 'setup' ? '준비 · ' : '테스트 · '}{item.caseId} · {statusLabels[item.status] || item.status}{item.httpStatus != null ? ` · HTTP ${item.httpStatus}` : ''}{item.errorCategory ? ` · ${item.errorCategory}` : ''}</li>)}</ul></div>}
    {(result.error || executionLog) && <div className="result-heading"><strong>실행 로그</strong></div>}
    {(result.error || executionLog) && <pre>{result.error || executionLog}</pre>}
  </section>
}

export { RunResult }
