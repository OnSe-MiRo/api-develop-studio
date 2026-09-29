import { useEffect, useState } from 'react'
import { api } from '../../utils/studio.js'
import { navigateTo } from '../../router.js'
import { absoluteDelta, chartSegments, comparisonMetrics, elapsedSeries, metricValue, metricVerdict, number, percent, provisionalCriteria, relativeDelta } from './comparison.js'

const time = value => value ? new Date(value).toLocaleString('ko-KR') : '—'
const metrics = [
  { key: 'rps', label: 'RPS', unit: 'req/s', format: number },
  { key: 'p95Ms', label: 'p95', unit: 'ms', format: number },
  { key: 'errorRate', label: '오류율', unit: '%', format: percent },
  { key: 'activeVus', label: '활성 VU', unit: '명', format: number },
  { key: 'cpuPercent', label: '서버 CPU', unit: '%', format: number },
  { key: 'memoryMb', label: '서버 메모리', unit: 'MB', format: number },
]
const conditions = [
  ['project', '프로젝트', detail => detail.run?.project],
  ['environment', '환경', detail => ['os', 'cpu', 'memoryMb', 'executionMode', 'k6Version'].map(key => `${key}: ${detail.run?.environment?.[key] ?? '미수집'}`).join(' · ')],
  ['vusMax', '최대 VU', detail => detail.summary?.vusMax],
  ['appVersion', '앱 버전', detail => detail.run?.appVersion],
  ['commitSha', 'Commit', detail => detail.run?.commitSha],
  ['status', '실행 상태', detail => ({ passed: '통과', failed: '실패', aborted: '중단', error: '오류' }[detail.run?.status] || '미수집')],
]

function Message({ children, error = false }) {
  return <div className={`load-state ${error ? 'load-error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>
}

function ScrollTable({ name, children }) {
  return <div className="load-table-scroll" role="region" aria-label={`${name} 가로 스크롤`} tabIndex={0}>{children}</div>
}

function ChangeCells({ change, metric }) {
  const verdict = metricVerdict(change, metric.direction)
  return <><td>{metricValue(change?.baseline, metric)}</td><td>{metricValue(change?.candidate, metric)}</td><td>{absoluteDelta(change, metric)}</td><td>{relativeDelta(change)}</td><td className={verdict.includes('악화') ? 'load-fail' : verdict.includes('개선') ? 'load-pass' : ''}>{verdict}</td></>
}

function Overlay({ baseline, candidate, baselineSeries, candidateSeries }) {
  const before = elapsedSeries(baselineSeries, baseline.run?.startedAt)
  const after = elapsedSeries(candidateSeries, candidate.run?.startedAt)
  const all = [...before, ...after]
  if (!all.length) return <Message>두 실행의 시간 추이 데이터가 없습니다.</Message>
  const maximumTime = Math.max(0, ...all.map(item => item.elapsed))
  const reduced = [baselineSeries, candidateSeries].some(series => series && series.aggregation !== 'none')
  return <>
    <p className="load-note">각 실행 시작을 0초로 맞춥니다. 같은 경과 시간과 공통 Y축으로 겹쳐 표시하며 측정값이 없는 지점은 연결하지 않습니다. 기준은 파란 실선, 비교는 주황 점선입니다.{reduced && ' 축소된 RPS·오류율·CPU·메모리는 평균, VU는 최대, p95는 구간별 p95 상한입니다. 전체 요청의 재계산 percentile이 아닙니다.'}</p>
    <div className="load-overlay-legend"><span>━ 기준: {baseline.run.id}</span><span>┄ 비교: {candidate.run.id}</span></div>
    <div className="load-charts" aria-label="경과 시간 비교 차트">{metrics.map(metric => {
      const values = all.map(item => item[metric.key]).filter(value => typeof value === 'number' && Number.isFinite(value))
      const maximum = Math.max(1, ...values)
      return <article className="load-chart" key={metric.key}><div className="load-chart-title"><strong>{metric.label}</strong><span>{values.length ? `최대 ${metric.format(Math.max(...values))}${metric.key === 'errorRate' ? '' : ` ${metric.unit}`}` : '측정값 없음'}</span></div>
        {values.length ? <svg viewBox="0 0 600 90" preserveAspectRatio="none" aria-hidden="true" focusable="false"><path d="M20 74H580" stroke="#cbd5e1" fill="none" />{[before, after].flatMap((items, index) => chartSegments(items, metric.key, maximumTime, maximum).map((segment, part) => segment.length === 1 ? <circle key={`${index}-${part}`} cx={segment[0].split(',')[0]} cy={segment[0].split(',')[1]} r="3" fill={index ? '#c2410c' : '#2563eb'} /> : <polyline key={`${index}-${part}`} points={segment.join(' ')} fill="none" stroke={index ? '#c2410c' : '#2563eb'} strokeDasharray={index ? '6 4' : undefined} strokeWidth="2.5" vectorEffect="non-scaling-stroke" />))}</svg> : <p className="hint">측정 데이터 없음</p>}
        <div className="load-chart-times"><span>0초</span><span>{number(maximumTime)}초</span></div></article>
    })}</div>
    <ScrollTable name="비교 추이 데이터 표"><table><caption>비교 추이 데이터 표 (차트와 동일한 데이터)</caption><thead><tr><th scope="col">실행</th><th scope="col">경과 시간</th><th scope="col">원래 시각</th>{metrics.map(metric => <th scope="col" key={metric.key}>{metric.label} ({metric.unit})</th>)}</tr></thead><tbody>{[...before.map(item => ({ ...item, label: '기준' })), ...after.map(item => ({ ...item, label: '비교' }))].sort((a, b) => a.elapsed - b.elapsed || a.label.localeCompare(b.label)).map(item => <tr key={`${item.label}-${item.bucketAt}`}><th scope="row">{item.label}</th><td>{number(item.elapsed)}초</td><td><time dateTime={item.bucketAt}>{time(item.bucketAt)}</time></td>{metrics.map(metric => <td key={metric.key}>{metric.format(item[metric.key])}</td>)}</tr>)}</tbody></table></ScrollTable>
  </>
}

function Criteria({ baseline, candidate }) {
  return <section className="card"><h2>통과 기준과 실행 Threshold</h2><p className="load-note">임시 기준은 서비스 SLO가 없는 상태의 참고 기준입니다. 일반 읽기와 고유 문서 저장은 Target 부하에서 각각 적용하며 /api/run 용량은 별도로 판단합니다. 현재 결과 형식은 적용 조건과 비예상 오류를 구분하지 않아 아래 기준의 자동 통과·실패 판정은 불가합니다. 실제 실행의 판정은 등록된 사용자 Threshold를 확인하세요.</p>
    <ScrollTable name="임시 통과 기준 표"><table><caption>계획의 임시 통과 기준 (참고용)</caption><thead><tr><th scope="col">항목</th><th scope="col">기준</th><th scope="col">현재 판정·적용 제한</th></tr></thead><tbody>{provisionalCriteria.map(([label, rule, reason]) => <tr key={label}><th scope="row">{label}</th><td>{rule}</td><td>판정 불가 · {reason}</td></tr>)}</tbody></table></ScrollTable>
    <ScrollTable name="두 실행 Threshold 표"><table><caption>두 실행의 사용자 지정 Threshold (등록된 판정)</caption><thead><tr><th scope="col">실행</th><th scope="col">지표</th><th scope="col">조건</th><th scope="col">실측값</th><th scope="col">판정</th></tr></thead><tbody>{[[baseline, '기준'], [candidate, '비교']].flatMap(([detail, label]) => detail.thresholds?.length ? detail.thresholds.map((item, index) => <tr key={`${label}-${index}`}><th scope="row">{label}</th><td>{item.metric}</td><td>{item.condition}</td><td>{number(item.actualValue, 4)}</td><td className={item.passed ? 'load-pass' : 'load-fail'}>{item.passed ? '✓ 통과' : '✕ 실패'}</td></tr>) : [<tr key={label}><th scope="row">{label}</th><td colSpan={4}>설정된 Threshold 없음</td></tr>])}</tbody></table></ScrollTable>
  </section>
}

export function LoadTestComparison({ route, refreshKey }) {
  const { baselineId = '', candidateId = '' } = route
  const selection = `${baselineId}\n${candidateId}`
  const [draft, setDraft] = useState({ baseline: baselineId, candidate: candidateId })
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [options, setOptions] = useState([])
  const [cursor, setCursor] = useState(null)
  const [optionsError, setOptionsError] = useState('')
  const [optionsBusy, setOptionsBusy] = useState(false)
  const [page, setPage] = useState('')
  useEffect(() => { setDraft({ baseline: baselineId, candidate: candidateId }) }, [selection])
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setOptionsBusy(true); setOptionsError('')
    api(`/api/load-tests/runs?limit=20${page ? `&cursor=${encodeURIComponent(page)}` : ''}`, { signal: controller.signal }).then(data => {
      if (!active) return
      setOptions(old => page ? [...old, ...(data.items || [])] : data.items || [])
      setCursor(data.nextCursor || null)
    }).catch(requestError => { if (active && requestError.name !== 'AbortError') setOptionsError(requestError.message) }).finally(() => { if (active) setOptionsBusy(false) })
    return () => { active = false; controller.abort() }
  }, [page, revision, refreshKey])
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setResult(null); setError('')
    if (!candidateId) return () => { active = false; controller.abort() }
    const runPath = id => `/api/load-tests/runs/${encodeURIComponent(id)}`
    async function load() {
      try {
        const candidate = await api(runPath(candidateId), { signal: controller.signal })
        if (!active) return
        if (!baselineId) {
          if (candidate.recommendedBaseline?.run?.id) {
            navigateTo({ ...route, tab: 'load-test-compare', baselineId: candidate.recommendedBaseline.run.id, candidateId }, { replace: true })
          } else setResult({ selection, candidate, recommendationOnly: true })
          return
        }
        const [baseline, comparison] = await Promise.all([
          api(runPath(baselineId), { signal: controller.signal }),
          api(`/api/load-tests/compare?${new URLSearchParams({ baseline: baselineId, candidate: candidateId })}`, { signal: controller.signal }),
        ])
        if (!active) return
        setResult({ selection, baseline, candidate, comparison })
        const series = await Promise.allSettled([api(`${runPath(baselineId)}/series?maxPoints=240`, { signal: controller.signal }), api(`${runPath(candidateId)}/series?maxPoints=240`, { signal: controller.signal })])
        if (active) setResult({ selection, baseline, candidate, comparison, baselineSeries: series[0].status === 'fulfilled' ? series[0].value : null, candidateSeries: series[1].status === 'fulfilled' ? series[1].value : null, seriesErrors: series.map((item, index) => item.status === 'rejected' ? `${index ? '비교' : '기준'}: ${item.reason.message}` : '').filter(Boolean) })
      } catch (requestError) { if (active && requestError.name !== 'AbortError') setError(requestError.message) }
    }
    load()
    return () => { active = false; controller.abort() }
  }, [selection, revision, refreshKey])
  const visible = result?.selection === selection ? result : null
  const { baseline, candidate, comparison } = visible || {}
  const known = [...options, ...(baseline ? [baseline] : []), ...(candidate ? [candidate] : [])]
  const unique = [...new Map(known.filter(item => item.run?.id).map(item => [item.run.id, item])).values()]
  const openComparison = event => {
    event.preventDefault()
    if (!draft.candidate.trim()) { setError('비교 실행 ID를 선택하세요.'); return }
    navigateTo({ ...route, tab: 'load-test-compare', baselineId: draft.baseline.trim(), candidateId: draft.candidate.trim() })
  }
  const recommend = candidate?.recommendedBaseline?.run?.id
  return <main className="load-dashboard">
    <div className="section-header"><div><button className="load-back" onClick={() => navigateTo({ tab: 'load-tests', loadFilters: route.loadFilters })}>← 결과 목록</button><p className="eyebrow">LOAD TEST COMPARISON</p><h1>실행 비교</h1><p className="hint">기준 대비 수치 변화와 회귀 후보를 확인합니다.</p></div><button className="ghost" onClick={() => setRevision(value => value + 1)}>↻ 결과 새로고침</button></div>
    <form className="card load-comparison-picker" onSubmit={openComparison}><label className="field" htmlFor="load-baseline"><span>기준 실행 ID</span><input id="load-baseline" list="load-comparison-runs" value={draft.baseline} onChange={event => setDraft(old => ({ ...old, baseline: event.target.value }))} placeholder="비워두면 이전 실행 자동 추천" /></label><label className="field" htmlFor="load-candidate"><span>비교 실행 ID</span><input id="load-candidate" list="load-comparison-runs" value={draft.candidate} onChange={event => setDraft(old => ({ ...old, candidate: event.target.value }))} placeholder="실행 ID 선택 또는 입력" /></label><datalist id="load-comparison-runs">{unique.map(item => <option key={item.run.id} value={item.run.id}>{item.run.project} · {item.run.scenario} · {time(item.run.startedAt)}</option>)}</datalist><button className="primary" type="submit">비교 적용</button><div className="load-picker-notes"><p className="hint">최근 실행을 제안합니다. 이전 실행도 ID로 직접 선택할 수 있습니다. 기준을 비우면 같은 프로젝트·시나리오·결과 형식의 직전 실행을 추천합니다.</p><button className="ghost" type="button" disabled={!cursor || optionsBusy} onClick={() => setPage(cursor)}>이전 실행 더 보기</button>{optionsError && <span role="alert">실행 제안 목록 오류: {optionsError}</span>}</div></form>
    {error && <Message error>{error}<button className="ghost" onClick={() => setRevision(value => value + 1)}>다시 시도</button></Message>}
    {!candidateId && !error && <Message>비교할 실행을 선택하세요.</Message>}
    {candidateId && !visible && !error && <Message>실행 비교를 불러오는 중입니다…</Message>}
    {visible?.recommendationOnly && <Message>같은 프로젝트·시나리오의 이전 실행이 없습니다. 기준 실행 ID를 직접 선택하세요.</Message>}
    {candidate && <section className="card load-recommendation"><h2>이전 실행 추천</h2><p className="hint">{recommend ? `${recommend} · ${time(candidate.recommendedBaseline.run.startedAt)}` : '추천 가능한 이전 실행 없음'} · 비교 실행의 시작 시각 이전을 우선하며 같은 시각은 실행 ID의 사전순으로 결정합니다.</p>{recommend && <button className="ghost" disabled={recommend === baselineId} onClick={() => navigateTo({ ...route, tab: 'load-test-compare', baselineId: recommend, candidateId })}>추천 기준 적용</button>}</section>}
    {baseline && candidate && comparison && <>
      <section className="card load-warnings"><h2>비교 조건 확인</h2><p className="hint">{comparison.conditionWarnings?.some(key => !['appVersion', 'commitSha'].includes(key)) ? '⚠ 비교 조건 다름. 아래 수치만으로 성능 회귀를 확정할 수 없습니다.' : '기록된 조건 차이 없음.'} 데이터셋 정보는 현재 결과 형식에 없어 동일성을 확인할 수 없습니다. 환경의 미수집 값도 동일성의 증거가 아닙니다. 앱 버전·Commit 차이는 변경 비교를 위한 참고 정보입니다.</p><ScrollTable name="비교 조건 표"><table><thead><tr><th scope="col">조건</th><th scope="col">기준</th><th scope="col">비교</th><th scope="col">확인</th></tr></thead><tbody>{conditions.map(([key, label, getter]) => <tr key={key}><th scope="row">{label}</th><td>{getter(baseline) ?? '미수집'}</td><td>{getter(candidate) ?? '미수집'}</td><td>{comparison.conditionWarnings?.includes(key) ? ['appVersion', 'commitSha'].includes(key) ? '정보: 다름' : '⚠ 다름' : key === 'environment' && [baseline, candidate].some(detail => ['os', 'cpu', 'memoryMb', 'executionMode', 'k6Version'].some(field => detail.run?.environment?.[field] == null || detail.run.environment[field] === '')) ? '미수집 항목 있음' : getter(baseline) == null || getter(baseline) === '' ? '미수집' : '같음'}</td></tr>)}<tr><th scope="row">데이터셋</th><td>미수집</td><td>미수집</td><td>확인 불가</td></tr></tbody></table></ScrollTable></section>
      <section className="card"><h2>핵심 지표 변화</h2><p className="hint">절대 차이 = 비교 − 기준, 증감률 = 차이 ÷ 기준 × 100. 오류율 차이는 %p입니다. 지연·오류율 증가와 RPS 감소를 악화 후보로 표시하며 0 기준은 상대 판정 불가입니다. 요청 수·VU는 실행 조건 변화입니다.</p><ScrollTable name="핵심 지표 변화 표"><table><thead><tr><th scope="col">지표</th><th scope="col">기준</th><th scope="col">비교</th><th scope="col">절대 차이</th><th scope="col">증감률</th><th scope="col">수치 판정</th></tr></thead><tbody>{comparisonMetrics.map(metric => <tr key={metric.key}><th scope="row">{metric.label}</th><ChangeCells change={comparison.metrics?.[metric.key]} metric={metric} /></tr>)}</tbody></table></ScrollTable></section>
      <section className="card"><h2>Endpoint 회귀 후보 · p95 악화순</h2><p className="hint">p95 절대 증가량 내림차순입니다. 임계 허용치는 0이며 양의 변화가 후보입니다. 오류율 변화도 별도로 표시합니다. 신규·제거 endpoint와 0 기준은 판정 불가이고, 조건과 데이터셋 확인 후 회귀 여부를 판단하세요.</p>{!comparison.endpoints?.length ? <Message>비교할 Endpoint 집계가 없습니다.</Message> : <ScrollTable name="Endpoint 비교 표"><table><thead><tr><th scope="col">Method · Endpoint</th><th scope="col">지표</th><th scope="col">기준</th><th scope="col">비교</th><th scope="col">절대 차이</th><th scope="col">증감률</th><th scope="col">수치 판정</th></tr></thead><tbody>{comparison.endpoints.flatMap(item => ['p95Ms', 'errorRate'].map((key, index) => <tr key={`${item.method}-${item.endpoint}-${key}`}>{index === 0 && <th scope="rowgroup" rowSpan={2} className="load-endpoint">{item.method} {item.endpoint}<small>{item.p95Ms?.baseline == null ? '신규 Endpoint' : item.p95Ms?.candidate == null ? '제거 Endpoint' : ''}</small></th>}<th scope="row">{key === 'p95Ms' ? 'p95' : '오류율'}</th><ChangeCells change={item[key]} metric={comparisonMetrics.find(metric => metric.key === key)} /></tr>))}</tbody></table></ScrollTable>}</section>
      <section className="card"><h2>두 실행의 시간 추이</h2>{visible.seriesErrors?.length > 0 && <Message error>추이 데이터 오류: {visible.seriesErrors.join(' · ')}. 요약 비교는 계속 확인할 수 있습니다.</Message>}{!visible.seriesErrors && <Message>시간 추이를 불러오는 중입니다…</Message>}{visible.seriesErrors && <Overlay baseline={baseline} candidate={candidate} baselineSeries={visible.baselineSeries} candidateSeries={visible.candidateSeries} />}</section>
      <Criteria baseline={baseline} candidate={candidate} />
    </>}
  </main>
}
