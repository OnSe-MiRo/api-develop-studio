import './contract-summary.css'

// Reports contain metadata only. Never render unknown fields or malformed values.
export function readContractSummary(value) {
  if (value == null) return { state: 'missing' }
  if (typeof value !== 'object' || Array.isArray(value) || typeof value.valid !== 'boolean' ||
      !Number.isSafeInteger(value.issueCount) || value.issueCount < 0 || value.issueCount > 100 ||
      typeof value.documentDigest !== 'string' || !/^[a-f0-9]{64}$/i.test(value.documentDigest) ||
      (value.valid ? value.issueCount !== 0 : value.issueCount === 0)) return { state: 'invalid' }
  return { state: value.valid ? 'passed' : 'failed', issueCount: value.issueCount, documentDigest: value.documentDigest.toLowerCase() }
}

export function ContractSummary({ contract }) {
  const summary = readContractSummary(contract)
  if (summary.state === 'missing') return <p className="contract-summary-muted">OpenAPI 계약 요약 없음</p>
  if (summary.state === 'invalid') return <p className="contract-summary-muted">OpenAPI 계약 요약 확인 불가</p>
  return <div className={`contract-summary contract-summary-${summary.state}`} role="group" aria-label="OpenAPI 계약 결과">
    <p><strong>{summary.state === 'passed' ? 'OpenAPI 계약 통과' : 'OpenAPI 계약 실패'}</strong><span> · 문제 {summary.issueCount}개</span></p>
    <details><summary>검사 명세 SHA-256</summary><code>{summary.documentDigest}</code><p className="hint">실행 당시 검사한 명세 스냅샷의 지문입니다.</p></details>
  </div>
}
