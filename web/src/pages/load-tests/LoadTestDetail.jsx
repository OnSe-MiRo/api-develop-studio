import { useEffect, useState } from 'react'
import { api } from '../../utils/studio.js'
import { navigateTo } from '../../router.js'
import { display, formatNumber, formatPercent, formatTime, StateMessage, Status } from './loadTestDisplay.jsx'
import './load-tests.css'

const metricDefinitions = [
  { key: 'rps', label: 'RPS', unit: 'req/s', color: '#2563eb', format: value => formatNumber(value) },
  { key: 'p95Ms', label: 'p95', unit: 'ms', color: '#7c3aed', format: value => formatNumber(value) },
  { key: 'errorRate', label: '오류율', unit: '%', color: '#dc2626', format: formatPercent },
  { key: 'activeVus', label: '활성 VU', unit: '명', color: '#0891b2', format: value => formatNumber(value, 0) },
  { key: 'cpuPercent', label: '서버 CPU', unit: '%', color: '#b45309', format: value => value == null ? '—' : `${formatNumber(value)}%` },
  { key: 'memoryMb', label: '서버 메모리', unit: 'MB', color: '#15803d', format: value => formatNumber(value) },
]

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

export function LoadTestDetail({ route, refreshKey }) {
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
