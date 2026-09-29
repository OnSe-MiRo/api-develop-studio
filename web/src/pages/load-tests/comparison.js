export const number = (value, digits = 2) => value == null ? '—' : Number(value).toLocaleString('ko-KR', { maximumFractionDigits: digits })
export const percent = value => value == null ? '—' : `${number(value * 100)}%`

export const comparisonMetrics = [
  { key: 'requests', label: '요청 수', unit: '건', direction: 'neutral' },
  { key: 'rps', label: 'RPS', unit: 'req/s', direction: 'higher' },
  { key: 'vusMax', label: '최대 VU', unit: '명', direction: 'neutral' },
  { key: 'p50Ms', label: 'p50', unit: 'ms', direction: 'lower' },
  { key: 'p95Ms', label: 'p95', unit: 'ms', direction: 'lower' },
  { key: 'p99Ms', label: 'p99', unit: 'ms', direction: 'lower' },
  { key: 'errorRate', label: '오류율', unit: '%', direction: 'lower' },
]

export function metricValue(value, metric) {
  return metric.key === 'errorRate' ? percent(value) : value == null ? '—' : `${number(value)} ${metric.unit}`
}

export function absoluteDelta(change, metric) {
  if (change?.delta == null) return '판정 불가'
  const delta = metric.key === 'errorRate' ? change.delta * 100 : change.delta
  return `${delta > 0 ? '+' : ''}${number(delta)} ${metric.key === 'errorRate' ? '%p' : metric.unit}`
}

export function relativeDelta(change) {
  return change?.changePercent == null ? '계산 불가' : `${change.changePercent > 0 ? '+' : ''}${number(change.changePercent)}%`
}

export function metricVerdict(change, direction = 'lower') {
  if (!change || change.baseline == null || change.candidate == null) return '판정 불가'
  if (change.baseline === 0 && change.candidate !== 0) return '판정 불가 (기준 0)'
  if (change.delta === 0) return '동일'
  if (direction === 'neutral') return '조건 변화'
  return (direction === 'higher' ? change.delta < 0 : change.delta > 0) ? '⚠ 악화 후보' : '✓ 개선'
}

export function elapsedSeries(series, startedAt) {
  const start = Date.parse(startedAt)
  return (series?.items || []).map(item => ({ ...item, elapsed: (Date.parse(item.bucketAt) - start) / 1000 }))
    .filter(item => Number.isFinite(item.elapsed) && item.elapsed >= 0)
}

export function chartSegments(items, key, timeMaximum, valueMaximum) {
  const segments = []
  let current = []
  for (const item of items) {
    const value = item[key]
    if (typeof value === 'number' && Number.isFinite(value)) {
      current.push(`${20 + (timeMaximum > 0 ? item.elapsed / timeMaximum : 0) * 560},${74 - value / valueMaximum * 58}`)
    } else if (current.length) {
      segments.push(current); current = []
    }
  }
  if (current.length) segments.push(current)
  return segments
}

export const provisionalCriteria = [
  ['일반 읽기 p95', 'Target 부하에서 ≤ 300 ms', '일반 읽기·Target 부하 구분 없음'],
  ['일반 읽기 p99', 'Target 부하에서 ≤ 1,000 ms', '일반 읽기·Target 부하 구분 없음'],
  ['고유 문서 저장 p95', 'Target 부하에서 ≤ 1,000 ms', '고유 문서 저장·Target 부하 구분 없음'],
  ['비예상 오류율', '< 1%', '예상 오류와 비예상 오류 구분 없음'],
  ['서버 오류', '정상 입력의 5xx 0건', '입력·응답 상태별 건수 없음'],
  ['경합 정확성', '예상 409 외 오류·revision 유실 0건', 'revision·경합 정확성 데이터 없음'],
  ['/api/run 정확성', '성공 대상 exitCode 오류·고아 프로세스 0건', '성공 대상 exitCode·프로세스 수명 정보 없음'],
  ['자원', 'CPU > 85% 또는 메모리 > 80%가 5분 지속되지 않음', '서버 메모리 사용률·지속 구간 검증 없음'],
  ['회복', 'Spike 후 5분 안에 p95·자원 ≤ Baseline의 120%', 'Spike 종료·회복 구간 정보 없음'],
  ['Soak', '2시간 동안 메모리·thread·WAL의 지속 증가 없음', 'Soak 구분·thread·WAL 정보 없음'],
]
