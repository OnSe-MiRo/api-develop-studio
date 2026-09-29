import { useEffect, useState } from 'react'
import { api } from '../../utils/studio.js'
import { navigateTo } from '../../router.js'
import { LoadTestComparison } from './LoadTestComparison.jsx'
import './load-tests.css'

const statusLabels = { passed: '통과', failed: '실패', aborted: '중단', error: '오류' }
const formatNumber = (value, digits = 2) => value == null ? '—' : Number(value).toLocaleString('ko-KR', { maximumFractionDigits: digits })
const formatPercent = value => value == null ? '—' : `${formatNumber(value * 100, 2)}%`
const formatTime = value => value ? new Date(value).toLocaleString('ko-KR') : '—'
const display = value => value === null || value === undefined || value === '' ? '—' : value
const metricDefinitions = [
  { key: 'rps', label: 'RPS', unit: 'req/s', color: '#2563eb', format: value => formatNumber(value) },
  { key: 'p95Ms', label: 'p95', unit: 'ms', color: '#7c3aed', format: value => formatNumber(value) },
  { key: 'errorRate', label: '오류율', unit: '%', color: '#dc2626', format: formatPercent },
  { key: 'activeVus', label: '활성 VU', unit: '명', color: '#0891b2', format: value => formatNumber(value, 0) },
  { key: 'cpuPercent', label: '서버 CPU', unit: '%', color: '#b45309', format: value => value == null ? '—' : `${formatNumber(value)}%` },
  { key: 'memoryMb', label: '서버 메모리', unit: 'MB', color: '#15803d', format: value => formatNumber(value) },
]

function StateMessage({ children, onRetry, error = false }) {
  return <div className={error ? 'load-state load-error' : 'load-state'} role={error ? 'alert' : 'status'}>{children}{onRetry && <button className="ghost" onClick={onRetry}>다시 시도</button>}</div>
}

function Status({ status }) {
  return <span className={`load-status ${status || 'unknown'}`}>{statusLabels[status] || display(status)}</span>
}

function MetricCard({ label, value, hint }) {
  return <article className="card load-metric"><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</article>
}

function SeriesChart({ items, metric }) {
  const values = items.map(item => item[metric.key])
  const finite = values.filter(value => typeof value === 'number' && Number.isFinite(value))
  const maximum = Math.max(1, ...finite)
  const times = items.map(item => Date.parse(item.bucketAt))
  const firstTime = times[0]
  const timeSpan = times.at(-1) - firstTime
  const x = index => 20 + (timeSpan > 0 && Number.isFinite(times[index]) ? (times[index] - firstTime) / timeSpan : items.length > 1 ? index / (items.length - 1) : 0) * 560
  const segments = []
  let segment = []
  values.forEach((value, index) => {
    if (typeof value === 'number' && Number.isFinite(value)) {
      segment.push(`${x(index)},${74 - (value / maximum) * 58}`)
    } else if (segment.length) {
      segments.push(segment)
      segment = []
    }
  })
  if (segment.length) segments.push(segment)
  return <article className="load-chart">
    <div className="load-chart-title"><strong>{metric.label}</strong><span>{finite.length ? `최대 ${metric.format(Math.max(...finite))}${metric.unit !== '%' ? ` ${metric.unit}` : ''}` : '측정값 없음'}</span></div>
    {finite.length === 0 ? <p className="hint">측정 데이터 없음</p> : <svg viewBox="0 0 600 90" preserveAspectRatio="none" aria-hidden="true" focusable="false">
      <path d="M20 74H580" stroke="#cbd5e1" fill="none" />
      {segments.map((points, index) => points.length === 1 ? <circle key={index} cx={points[0].split(',')[0]} cy={points[0].split(',')[1]} r="3" fill={metric.color} /> : <polyline key={index} points={points.join(' ')} fill="none" stroke={metric.color} strokeWidth="2.5" vectorEffect="non-scaling-stroke" />)}
    </svg>}
    <div className="load-chart-times"><span>{formatTime(items[0]?.bucketAt)}</span><span>{formatTime(items.at(-1)?.bucketAt)}</span></div>
  </article>
}

function Trend({ series }) {
  const items = series?.items || []
  if (!items.length) return <StateMessage>시간 추이 데이터가 없습니다. 요약 지표와 표는 계속 확인할 수 있습니다.</StateMessage>
  return <>
    {series.aggregation !== 'none' && <p className="load-note">차트는 {formatNumber(series.sourcePoints, 0)}개 구간을 축소했습니다. RPS·오류율·CPU·메모리는 평균, VU는 최대값, p95는 구간별 p95의 상한입니다. 축소 p95는 전체 요청의 재계산 percentile이 아닙니다.</p>}
    <div className="load-charts" aria-label="시간 추이 차트">{metricDefinitions.map(metric => <SeriesChart key={metric.key} items={items} metric={metric} />)}</div>
    <div className="load-table-scroll" role="region" aria-label="시간 추이 데이터 표 가로 스크롤" tabIndex={0}><table><caption>시간 추이 데이터 표 (차트와 동일한 데이터)</caption><thead><tr><th scope="col">시각</th>{metricDefinitions.map(metric => <th scope="col" key={metric.key}>{metric.label}</th>)}</tr></thead><tbody>{items.map(item => <tr key={item.bucketAt}><td><time dateTime={item.bucketAt}>{formatTime(item.bucketAt)}</time></td>{metricDefinitions.map(metric => <td key={metric.key}>{metric.format(item[metric.key])}</td>)}</tr>)}</tbody></table></div>
  </>
}

function LoadList({ route, projects, projectDetails, refreshKey }) {
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
  const projectOptions = projects.includes(filters.project) || !filters.project ? projects : [filters.project, ...projects]
  const visibleProjects = [...new Set([...projectOptions, ...(data?.items || []).map(item => item.run?.project).filter(Boolean)])]
  return <main className="load-dashboard">
    <div className="section-header"><div><p className="eyebrow">LOAD TEST RESULTS</p><h1>부하테스트 결과</h1><p className="hint">저장된 실행 결과의 성능 지표와 통과 조건을 확인합니다. 날짜 필터는 UTC 기준입니다.</p></div><button className="ghost" onClick={() => setRevision(value => value + 1)}>↻ 결과 새로고침</button></div>
    <form className="card load-filters" onSubmit={apply}>
      <label className="field" htmlFor="load-project-filter"><span>프로젝트</span><input id="load-project-filter" list="load-projects" value={draft.project || ''} onChange={event => updateDraft('project', event.target.value)} placeholder="전체 프로젝트" /></label><datalist id="load-projects">{visibleProjects.map(reference => <option key={reference} value={reference}>{projectDetails[reference]?.name || reference}</option>)}</datalist>
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

function LoadDetail({ route, refreshKey }) {
  const [detail, setDetail] = useState(null)
  const [series, setSeries] = useState(null)
  const [detailError, setDetailError] = useState('')
  const [seriesError, setSeriesError] = useState('')
  const [revision, setRevision] = useState(0)
  const runId = route.runId
  useEffect(() => {
    if (!runId) return
    const controller = new AbortController()
    setDetail(null); setSeries(null); setDetailError(''); setSeriesError('')
    const path = `/api/load-tests/runs/${encodeURIComponent(runId)}`
    api(path, { signal: controller.signal }).then(setDetail).catch(error => { if (error.name !== 'AbortError') setDetailError(error.message) })
    api(`${path}/series?maxPoints=240`, { signal: controller.signal }).then(setSeries).catch(error => { if (error.name !== 'AbortError') setSeriesError(error.message) })
    return () => controller.abort()
  }, [runId, revision, refreshKey])
  const goBack = () => navigateTo({ tab: 'load-tests', loadFilters: route.loadFilters })
  const run = detail?.run || {}
  const summary = detail?.summary || {}
  return <main className="load-dashboard">
    <div className="section-header"><div><button className="load-back" onClick={goBack}>← 결과 목록</button><p className="eyebrow">LOAD TEST RESULT</p><h1>{run?.scenario || '실행 상세'}</h1><p className="hint load-run-id">{display(run?.id || runId)}</p></div><button className="ghost" onClick={() => setRevision(value => value + 1)}>↻ 결과 새로고침</button></div>
    {!runId && <StateMessage error>실행 ID가 없습니다. 목록에서 결과를 선택하세요.</StateMessage>}
    {runId && detailError && <StateMessage error onRetry={() => setRevision(value => value + 1)}>{detailError}</StateMessage>}
    {runId && !detail && !detailError && <StateMessage>실행 상세를 불러오는 중입니다…</StateMessage>}
    {detail && <>
      {(!detail.run || !detail.summary) && <StateMessage error>상세 결과 일부가 누락되었습니다. 표시 가능한 데이터만 확인하세요.</StateMessage>}
      <section className="load-kpis" aria-label="실행 요약">
        <MetricCard label="실행 결과" value={<Status status={run.status} />} hint={summary?.thresholdsPassed ? 'Threshold 모두 통과' : '실패한 Threshold 확인'} />
        <MetricCard label="요청 수" value={formatNumber(summary?.requests, 0)} />
        <MetricCard label="RPS" value={formatNumber(summary?.rps)} />
        <MetricCard label="최대 VU" value={formatNumber(summary?.vusMax, 0)} />
        <MetricCard label="p50 / p95 / p99" value={`${formatNumber(summary?.latencyMs?.p50)} / ${formatNumber(summary?.latencyMs?.p95)} / ${formatNumber(summary?.latencyMs?.p99)} ms`} />
        <MetricCard label="오류율" value={formatPercent(summary?.errorRate)} />
      </section>
      <section className="card load-recommendation"><div><h2>실행 비교</h2><p className="hint">같은 프로젝트·시나리오의 이전 실행을 추천하고 수치 변화와 조건을 확인합니다.</p></div><button className="primary" onClick={() => navigateTo({ tab: 'load-test-compare', candidateId: runId, loadFilters: route.loadFilters })}>이전 실행과 비교</button></section>
      {run.status === 'aborted' && <StateMessage error>실행이 중단되었습니다. 종료 시각: {formatTime(run.endedAt)}</StateMessage>}
      {!!detail.warnings?.length && <section className="card load-warnings"><h2>가져오기 경고</h2><ul>{detail.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></section>}
      <section className="card"><h2>시간 추이</h2><p className="hint">차트와 아래 표는 같은 구간 데이터입니다. 측정하지 않은 서버 지표는 —로 표시합니다.</p>{seriesError && <StateMessage error onRetry={() => setRevision(value => value + 1)}>추이 데이터 오류: {seriesError}. 요약과 표는 계속 볼 수 있습니다.</StateMessage>}{!series && !seriesError && <StateMessage>시간 추이를 불러오는 중입니다…</StateMessage>}{series && <Trend series={series} />}</section>
      <section className="card"><h2>Threshold</h2>{!detail.thresholds?.length ? <StateMessage>설정된 Threshold가 없습니다.</StateMessage> : <div className="load-table-scroll" role="region" aria-label="Threshold 표 가로 스크롤" tabIndex={0}><table><thead><tr><th scope="col">지표</th><th scope="col">조건</th><th scope="col">실측값</th><th scope="col">판정</th></tr></thead><tbody>{detail.thresholds.map((item, index) => <tr key={`${item.metric}-${item.condition}-${index}`}><td>{item.metric}</td><td>{item.condition}</td><td>{formatNumber(item.actualValue, 4)}</td><td><span className={item.passed ? 'load-pass' : 'load-fail'}>{item.passed ? '✓ 통과' : '✕ 실패'}</span></td></tr>)}</tbody></table></div>}</section>
      <section className="card"><h2>Endpoint 집계</h2>{!detail.endpointMetrics?.length ? <StateMessage>Endpoint 집계가 없습니다.</StateMessage> : <div className="load-table-scroll" role="region" aria-label="Endpoint 집계 표 가로 스크롤" tabIndex={0}><table><thead><tr><th scope="col">Method</th><th scope="col">Endpoint</th><th scope="col">요청 수</th><th scope="col">p95</th><th scope="col">p99</th><th scope="col">오류율</th><th scope="col">상태</th></tr></thead><tbody>{detail.endpointMetrics.map((item, index) => <tr key={`${item.method}-${item.endpoint}-${index}`}><td>{item.method}</td><td className="load-endpoint">{item.endpoint}</td><td>{formatNumber(item.requestCount, 0)}</td><td>{formatNumber(item.latencyMs?.p95)} ms</td><td>{formatNumber(item.latencyMs?.p99)} ms</td><td>{formatPercent(item.errorRate)}</td><td>{item.errorRate > 0 ? '오류 있음' : '오류 없음'}</td></tr>)}</tbody></table></div>}</section>
      <section className="card load-environment"><h2>실행 환경</h2><dl><div><dt>프로젝트</dt><dd>{display(run.project)}</dd></div><div><dt>App version</dt><dd>{display(run.appVersion)}</dd></div><div><dt>Commit</dt><dd>{display(run.commitSha)}</dd></div><div><dt>OS</dt><dd>{display(run.environment?.os)}</dd></div><div><dt>CPU</dt><dd>{display(run.environment?.cpu)}</dd></div><div><dt>메모리</dt><dd>{run.environment?.memoryMb == null ? '—' : `${formatNumber(run.environment.memoryMb)} MB`}</dd></div><div><dt>실행 방식</dt><dd>{display(run.environment?.executionMode)}</dd></div><div><dt>k6</dt><dd>{display(run.environment?.k6Version)}</dd></div><div><dt>시작</dt><dd>{formatTime(run.startedAt)}</dd></div><div><dt>종료</dt><dd>{formatTime(run.endedAt)}</dd></div></dl></section>
    </>}
  </main>
}

export function LoadTestDashboard({ route, projects, projectDetails, refreshKey }) {
  if (route.tab === 'load-test-compare') return <LoadTestComparison route={route} refreshKey={refreshKey} />
  return route.tab === 'load-test-result' ? <LoadDetail route={route} refreshKey={refreshKey} /> : <LoadList route={route} projects={projects} projectDetails={projectDetails} refreshKey={refreshKey} />
}
