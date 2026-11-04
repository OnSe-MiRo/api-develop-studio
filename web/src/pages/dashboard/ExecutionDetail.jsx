import { ContractSummary, readContractSummary } from '../../components/ContractSummary.jsx'
import { useEffect, useRef, useState } from 'react'
import { api } from '../../utils/studio.js'
import { useRunJob } from '../../hooks/useRunJob.js'
import { normalizeOutcomeSearch } from '../../router.js'
import { RunResult } from '../../components/RunResult.jsx'

const labels = { passed: '성공', failed: '실패', error: '오류', timeout: '시간 초과', cancelled: '취소' }

export function ExecutionDetail({ runId, onClose, outcomeFilter = 'all', onOutcomeFilterChange, outcomeSearch = '', onOutcomeSearchChange }) {
  const heading = useRef(null)
  useEffect(() => { heading.current?.focus() }, [runId])
  const [run, setRun] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [searchInput, setSearchInput] = useState(outcomeSearch)
  useEffect(() => { setSearchInput(outcomeSearch) }, [runId, outcomeSearch])
  const job = useRunJob(`history:${runId}`)
  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    setRun(null)
    setError('')
    api(`/api/executions/${encodeURIComponent(runId)}`, { signal: controller.signal })
      .then(value => { if (!disposed) setRun(value) })
      .catch(reason => { if (!disposed && reason.name !== 'AbortError') setError(reason.message) })
    return () => { disposed = true; controller.abort() }
  }, [runId, revision])
  const outcomes = run?.detail?.outcomes || []
  const failures = outcomes.filter(item => ['failed', 'error', 'timeout', 'cancelled'].includes(item.status))
  const contractFailures = outcomes.filter(item => readContractSummary(item.contract).state === 'failed')
  const filteredOutcomes = outcomeFilter === 'failures' ? failures : outcomeFilter === 'contract' ? contractFailures : outcomes
  const query = outcomeSearch.toLowerCase()
  const visibleOutcomes = filteredOutcomes.filter(item => !query || [item.caseReference, item.caseId].some(value => typeof value === 'string' && value.toLowerCase().includes(query)))
  const rerun = async () => {
    try { await job.start({}, `/api/executions/${encodeURIComponent(runId)}/rerun`) }
    catch { /* useRunJob displays the submission error. */ }
  }
  return <section className="card execution-detail" aria-label="실행 상세">
    <div className="section-header"><h2 ref={heading} tabIndex={-1}>실행 상세</h2><button onClick={onClose}>상세 닫기</button></div>
    <code className="dashboard-run-id">{runId}</code>
    {error && <p role="alert">{error} <button onClick={() => setRevision(value => value + 1)}>상세 다시 시도</button></p>}
    {!run && !error && <p role="status">실행 상세를 불러오는 중입니다…</p>}
    {run && <>
      <dl className="execution-metadata">
        {[['결과', labels[run.status]], ['요청 환경', run.environment || '프로젝트 기본 설정'], ['실행자', run.actor], ['앱 버전', run.appVersion], ['Commit', run.commit], ['시작', run.startedAt], ['종료', run.finishedAt]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || '미수집'}</dd></div>)}
      </dl>
      {Object.keys(run.detail?.projectEnvironments || {}).length > 0 && <div><h3>실행 시 프로젝트 환경</h3><ul>{Object.entries(run.detail.projectEnvironments).map(([project, environment]) => <li key={project}>{project} · {environment === '' ? '기본 URL' : environment ?? '미수집'}</li>)}</ul></div>}
      {!run.detail?.reportAvailable && <p className="hint">상세 보고서가 수집되지 않은 실행입니다. 기존 이력 또는 중단된 실행은 assertion 결과가 없을 수 있습니다.</p>}
      <label>상세 항목 필터<select value={outcomeFilter} onChange={event => onOutcomeFilterChange(event.target.value)}>
        <option value="all">전체 ({outcomes.length})</option>
        <option value="failures">실패·오류·중단 ({failures.length})</option>
        <option value="contract">OpenAPI 계약 실패 ({contractFailures.length})</option>
      </select></label>
      <form className="dashboard-search" onSubmit={event => { event.preventDefault(); onOutcomeSearchChange(normalizeOutcomeSearch(searchInput)) }}>
        <label className="field"><span>상세 케이스 이름·경로 검색</span><input aria-label="상세 케이스 이름·경로 검색" maxLength={200} value={searchInput} onChange={event => setSearchInput(event.target.value)} /></label>
        <button type="submit">상세 검색</button>
        <button type="button" disabled={!searchInput && !outcomeSearch} onClick={() => { setSearchInput(''); onOutcomeSearchChange('') }}>상세 검색 초기화</button>
      </form>
      <p className="hint" role="status">수집된 상세 {outcomes.length}개 중 {visibleOutcomes.length}개 표시</p>
      {outcomeFilter === 'contract' && <p className="hint">유효한 계약 실패 요약이 있는 항목만 표시합니다. 요약 없음·확인 불가는 전체에서 확인하세요.</p>}
      {visibleOutcomes.length === 0 && <p>{outcomes.length === 0 ? '수집된 상세 항목이 없습니다.' : '선택한 조건에 맞는 상세 항목이 없습니다.'}</p>}
      <ul className="execution-outcomes">{visibleOutcomes.map((item, index) => <li key={`${outcomeFilter}:${index}`}>
        <strong>{item.caseReference || item.caseId}</strong> · {labels[item.status] || item.status}
        <p>{item.phase || 'test'} · HTTP {item.httpStatus ?? '—'} · {item.elapsedMs == null ? '—' : `${item.elapsedMs} ms`} · 시도 {item.attempts ?? 0}회</p>
        {item.errorCategory && <p>실패 분류: {item.errorCategory}</p>}
        <ContractSummary contract={item.contract} />
        {(item.assertions || []).some(assertion => !assertion.passed) && <p className="dashboard-negative">실패 assertion (0부터 시작): {(item.assertions || []).filter(assertion => !assertion.passed).map(assertion => assertion.index).join(', ')}</p>}
      </li>)}</ul>
      {run.rerunRequest ? <>
        <p className="hint">상세 항목 필터와 검색은 재실행 대상에 영향을 주지 않습니다. 현재 저장된 케이스·파이프라인과 현재 인증 설정으로 다시 실행합니다. 파이프라인은 준비·정리 단계를 포함합니다. 실패를 특정할 상세가 없으면 원래 저장 대상 전체를 재실행합니다.</p>
        <ul>{[...run.rerunRequest.cases, ...run.rerunRequest.pipelines].map(reference => <li key={reference}>{reference}</li>)}</ul>
        <button className="primary" disabled={job.busy} onClick={rerun}>실패 대상 재실행</button>
      </> : <p className="hint">재실행할 저장된 실패 대상이 없습니다. 저장 전 실행과 과거 상세 미수집 이력은 재실행할 수 없습니다.</p>}
    </>}
    <RunResult result={job.result} onCancel={job.cancel} />
  </section>
}
