import { useReferencePage } from '../../components/ReferencePicker.jsx'
import { useEffect, useState } from 'react'
import { api } from '../../utils/studio.js'
import { navigateTo } from '../../router.js'
import { display, formatNumber, formatPercent, formatTime, StateMessage, Status, statusLabels } from './loadTestDisplay.jsx'
import './load-tests.css'

export function LoadTestList({ route, refreshKey }) {
  const filters = route.loadFilters || {}
  const [draft, setDraft] = useState(filters)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [recent, setRecent] = useState(null)
  const filterKey = JSON.stringify(filters)

  useEffect(() => { setDraft(filters) }, [filterKey])
  useEffect(() => {
    const controller = new AbortController()
    setData(null); setError(''); setRecent(null)
    const query = new URLSearchParams({ limit: '20' })
    if (filters.project) query.set('project', filters.project)
    for (const name of ['scenario', 'status', 'cursor']) if (filters[name]) query.set(name, filters[name])
    if (filters.from) query.set('from', `${filters.from}T00:00:00Z`)
    if (filters.to) query.set('to', `${filters.to}T23:59:59.999999Z`)
    api(`/api/load-tests/runs?${query}`, { signal: controller.signal }).then(result => {
      setData(result)
      const first = result.items?.[0]?.run
      if (!first) return
      const latestQuery = new URLSearchParams({ project: first.project, scenario: first.scenario, limit: '2' })
      return api(`/api/load-tests/runs?${latestQuery}`, { signal: controller.signal }).then(latest => setRecent(latest.items)).catch(requestError => {
        if (requestError.name !== 'AbortError') setRecent([])
      })
    }).catch(requestError => { if (requestError.name !== 'AbortError') setError(requestError.message) })
    return () => controller.abort()
  }, [filterKey, revision, refreshKey])

  const updateDraft = (name, value) => setDraft(current => ({ ...current, [name]: value }))
  const apply = event => {
    event.preventDefault()
    if (draft.from && draft.to && draft.from > draft.to) { setError('시작일은 종료일보다 늦을 수 없습니다.'); return }
    navigateTo({ tab: 'load-tests', loadFilters: { ...draft, scenario: draft.scenario?.trim() || '', cursor: '' } })
  }
  const latest = recent?.[0]
  const previous = recent?.[1]
  const delta = (current, before, unit) => current == null || before == null ? '—' : `${current - before > 0 ? '+' : ''}${formatNumber(unit === '%p' ? (current - before) * 100 : current - before)}${unit}`
  const { page: suggestions } = useReferencePage('projects', '', draft.project?.trim().slice(0, 100) || '', '', refreshKey)
  const visibleProjects = [...new Set([...suggestions.items, ...(data?.items || []).map(item => item.run?.project).filter(Boolean)])]
  return <main className="load-dashboard">
    <div className="section-header"><div><p className="eyebrow">LOAD TEST RESULTS</p><h1>부하테스트 결과</h1><p className="hint">저장된 실행 결과의 성능 지표와 통과 조건을 확인합니다. 날짜 필터는 UTC 기준입니다.</p></div><button className="ghost" onClick={() => setRevision(value => value + 1)}>↻ 결과 새로고침</button></div>
    <form className="card load-filters" onSubmit={apply}>
      <label className="field" htmlFor="load-project-filter"><span>프로젝트</span><input id="load-project-filter" list="load-projects" value={draft.project || ''} onChange={event => updateDraft('project', event.target.value)} placeholder="전체 프로젝트" /></label><datalist id="load-projects">{visibleProjects.map(reference => <option key={reference} value={reference}>{suggestions.details?.[reference]?.name || reference}</option>)}</datalist>
      <label className="field"><span>시나리오</span><input value={draft.scenario || ''} onChange={event => updateDraft('scenario', event.target.value)} placeholder="시나리오 이름" /></label>
      <label className="field"><span>상태</span><select value={draft.status || ''} onChange={event => updateDraft('status', event.target.value)}><option value="">전체 상태</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="field"><span>시작일 (UTC)</span><input type="date" value={draft.from || ''} onChange={event => updateDraft('from', event.target.value)} /></label>
      <label className="field"><span>종료일 (UTC)</span><input type="date" value={draft.to || ''} onChange={event => updateDraft('to', event.target.value)} /></label>
      <div className="load-filter-actions"><button className="primary" type="submit">조회</button><button className="ghost" type="button" onClick={() => navigateTo({ tab: 'load-tests' })}>초기화</button></div>
    </form>
    {error && <StateMessage error onRetry={() => setRevision(value => value + 1)}>{error}</StateMessage>}
    {!data && !error && <StateMessage>결과 목록을 불러오는 중입니다…</StateMessage>}
    {data && <>
      {latest && previous && <section className="card load-recent"><h2>최근 같은 시나리오 변화</h2><p className="hint">{latest.run.project} · {latest.run.scenario} · 최근 실행 {formatTime(latest.run.startedAt)}과 직전 실행의 단순 차이</p><div className="load-recent-values"><span>p95 변화 <strong>{delta(latest.summary?.latencyMs?.p95, previous.summary?.latencyMs?.p95, ' ms')}</strong></span><span>오류율 변화 <strong>{delta(latest.summary?.errorRate, previous.summary?.errorRate, '%p')}</strong></span></div><p className="hint">{latest.schemaVersion !== previous.schemaVersion ? '결과 형식이 다릅니다. ' : ''}{latest.summary?.vusMax !== previous.summary?.vusMax ? '최대 VU가 다릅니다. ' : ''}{latest.run.appVersion !== previous.run.appVersion ? '앱 버전이 다릅니다. ' : ''}환경·데이터셋 동일성은 확인되지 않았습니다. 실행 조건이 다를 수 있으므로 이 값만으로 성능 회귀를 판단하지 마세요.</p></section>}
      {data.items?.some(item => !item.summary || !item.run) && <StateMessage>일부 결과의 요약 데이터가 누락되어 해당 항목은 제한적으로 표시됩니다.</StateMessage>}
      <section className="card load-list"><div className="section-header"><h2>실행 목록</h2><span className="hint">한 페이지에 최대 20건</span></div>
        {!data.items?.length ? <StateMessage>조회 조건에 맞는 결과가 없습니다.</StateMessage> : <div className="load-table-scroll" role="region" aria-label="실행 목록 표 가로 스크롤" tabIndex={0}><table><thead><tr><th scope="col">실행 시각·시나리오</th><th scope="col">프로젝트·버전</th><th scope="col">상태</th><th scope="col">최대 VU</th><th scope="col">RPS</th><th scope="col">p95</th><th scope="col">오류율</th><th scope="col">Threshold</th></tr></thead><tbody>{data.items.map((item, index) => <tr key={item.run?.id || index}><td><button className="load-result-link" onClick={() => navigateTo({ tab: 'load-test-result', runId: item.run?.id, loadFilters: filters })} disabled={!item.run?.id}>{formatTime(item.run?.startedAt)}<strong>{display(item.run?.scenario)}</strong></button></td><td><span>{display(item.run?.project)}</span><small>{item.run?.appVersion ? `v${item.run.appVersion}` : display(item.run?.commitSha)}</small></td><td><Status status={item.run?.status} /></td><td>{formatNumber(item.summary?.vusMax, 0)}</td><td>{formatNumber(item.summary?.rps)}</td><td>{item.summary?.latencyMs?.p95 == null ? '—' : `${formatNumber(item.summary.latencyMs.p95)} ms`}</td><td>{formatPercent(item.summary?.errorRate)}</td><td>{item.summary?.thresholdsPassed == null ? '—' : item.summary.thresholdsPassed ? '✓ 통과' : '✕ 실패'}</td></tr>)}</tbody></table></div>}
        <div className="load-pagination"><button className="ghost" disabled={!filters.cursor} onClick={() => navigateTo({ tab: 'load-tests', loadFilters: { ...filters, cursor: '' } })}>첫 페이지</button><button className="ghost" disabled={!data.nextCursor} onClick={() => navigateTo({ tab: 'load-tests', loadFilters: { ...filters, cursor: data.nextCursor } })}>다음 페이지 →</button></div>
      </section>
    </>}
  </main>
}
