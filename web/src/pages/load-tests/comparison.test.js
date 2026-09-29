import { describe, expect, it } from 'vitest'
import { absoluteDelta, chartSegments, elapsedSeries, metricVerdict, relativeDelta } from './comparison.js'

describe('load-test comparison calculations and semantics', () => {
  it('distinguishes ratio percentage points from relative percent', () => {
    const change = { baseline: .25, candidate: .5, delta: .25, changePercent: 100 }
    expect(absoluteDelta(change, { key: 'errorRate' })).toBe('+25 %p')
    expect(relativeDelta(change)).toBe('+100%')
    expect(absoluteDelta({ delta: 38.5 }, { key: 'p95Ms', unit: 'ms' })).toBe('+38.5 ms')
  })
  it('uses latency and RPS directions and leaves zero, missing and condition changes unjudged', () => {
    const growth = { baseline: 100, candidate: 120, delta: 20, changePercent: 20 }
    expect(metricVerdict(growth)).toBe('⚠ 악화 후보')
    expect(metricVerdict(growth, 'higher')).toBe('✓ 개선')
    expect(metricVerdict({ baseline: 120, candidate: 100, delta: -20 }, 'higher')).toBe('⚠ 악화 후보')
    expect(metricVerdict(growth, 'neutral')).toBe('조건 변화')
    expect(metricVerdict({ baseline: 0, candidate: 10, delta: 10 })).toBe('판정 불가 (기준 0)')
    expect(relativeDelta({ baseline: 0, delta: 10, changePercent: null })).toBe('계산 불가')
    expect(metricVerdict({ baseline: null, candidate: 10 })).toBe('판정 불가')
    expect(metricVerdict({ baseline: 10, candidate: null })).toBe('판정 불가')
    expect(metricVerdict({ baseline: 0, candidate: 0, delta: 0 })).toBe('동일')
  })
  it('aligns differently started runs on elapsed seconds without bridging missing measurements', () => {
    const first = elapsedSeries({ items: [{ bucketAt: '2026-09-28T00:00:05Z', rps: 10 }, { bucketAt: '2026-09-28T00:00:10Z', rps: null }, { bucketAt: '2026-09-28T00:00:20Z', rps: 20 }] }, '2026-09-28T00:00:00Z')
    const second = elapsedSeries({ items: [{ bucketAt: '2026-09-28T01:00:05Z', rps: 10 }, { bucketAt: '2026-09-28T01:00:20Z', rps: 20 }] }, '2026-09-28T01:00:00Z')
    expect(first.map(item => item.elapsed)).toEqual([5, 10, 20])
    expect(second.map(item => item.elapsed)).toEqual([5, 20])
    expect(chartSegments(first, 'rps', 20, 20)).toEqual([['160,45'], ['580,16']])
    expect(chartSegments(second, 'rps', 20, 20)).toEqual([['160,45', '580,16']])
  })
})
