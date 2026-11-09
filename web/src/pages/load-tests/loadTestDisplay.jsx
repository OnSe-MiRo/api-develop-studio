export const statusLabels = { passed: '통과', failed: '실패', aborted: '중단', error: '오류' }
export const formatNumber = (value, digits = 2) => value == null ? '—' : Number(value).toLocaleString('ko-KR', { maximumFractionDigits: digits })
export const formatPercent = value => value == null ? '—' : `${formatNumber(value * 100, 2)}%`
export const formatTime = value => value ? new Date(value).toLocaleString('ko-KR') : '—'
export const display = value => value === null || value === undefined || value === '' ? '—' : value

export function StateMessage({ children, onRetry, error = false }) {
  return <div className={error ? 'load-state load-error' : 'load-state'} role={error ? 'alert' : 'status'}>{children}{onRetry && <button className="ghost" onClick={onRetry}>다시 시도</button>}</div>
}

export function Status({ status }) {
  return <span className={`load-status ${status || 'unknown'}`}>{statusLabels[status] || display(status)}</span>
}
