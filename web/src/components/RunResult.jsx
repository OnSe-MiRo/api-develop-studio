import { asText } from '../utils/studio.js'

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
    {result.historyWarning && <p className="notice" role="alert">{result.historyWarning}</p>}
    {result.runId && <div className="result-heading"><span>Run ID: <code>{result.runId}</code></span></div>}
    <div className="result-heading"><strong>{result.error ? '실행 오류' : result.exitCode ? `실행 실패 (종료 코드 ${result.exitCode})` : '실행 완료'}</strong></div>
    {apiCallResults.length > 0 && <div style={{ padding: '14px', borderTop: '1px solid #dbe4f0', background: '#f8fbff' }}><strong style={{ color: '#334155', fontSize: 13 }}>API 호출 결과</strong><pre style={{ maxHeight: 260, margin: '10px 0 0', border: '1px solid #dbe4f0', borderRadius: 8 }}>{apiCallResults.map((value, index) => `${apiCallResults.length > 1 ? `호출 ${index + 1}\n` : ''}${value}`).join('\n\n')}</pre></div>}
    <div className="result-heading"><strong>실행 로그</strong></div>
    <pre>{result.error || executionLog}</pre>
  </section>
}

export { RunResult }
