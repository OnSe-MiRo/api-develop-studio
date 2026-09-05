import { useEffect, useState } from 'react'
import './dashboard.css'

const statusLabels = { passed: '성공', failed: '실패', error: '오류', timeout: '시간 초과' }
const duration = value => value == null ? '—' : value < 1000 ? `${Math.round(value).toLocaleString('ko-KR')} ms` : `${(value / 1000).toLocaleString('ko-KR', { maximumFractionDigits: 2 })} 초`
const count = value => value.toLocaleString('ko-KR')

export default function ExecutionDashboard({ projects, projectDetails, projectRef, onProjectChange, onNavigate, refreshKey }) {
  const [days, setDays] = useState(7)
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState(null)

  useEffect(() => {
    let controller
    let disposed = false
    setData(null)
    setError('')
    const load = async () => {
      controller?.abort()
      controller = new AbortController()
      const request = controller
      try {
        const query = new URLSearchParams({ project: projectRef, days, status, page })
        const response = await fetch(`/api/dashboard?${query}`, { signal: request.signal })
        const result = await response.json()
        if (!response.ok) throw new Error(result.error || '실행 이력을 불러오지 못했습니다.')
        if (disposed || request.signal.aborted) return
        setData(result)
        setUpdatedAt(new Date())
        setError('')
      } catch (requestError) {
        if (!disposed && !request.signal.aborted) setError(requestError.message)
      }
    }
    load()
    const timer = setInterval(load, 15000)
    return () => { disposed = true; controller?.abort(); clearInterval(timer) }
  }, [projectRef, days, status, page, revision, refreshKey])

  const changeProject = reference => { setPage(1); onProjectChange(reference) }
  const summary = data?.summary
  const maximum = Math.max(1, ...(data?.trend.map(day => day.total) || []))
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1
  return <main className="execution-dashboard">
    <div className="section-header">
      <div><p className="eyebrow">API EXECUTION</p><h1>API 실행 대시보드</h1><p className="hint">프로젝트의 실행 결과와 품질을 확인하세요. 완료된 실행을 15초마다 갱신합니다.</p></div>
      <div className="actions"><button onClick={() => setRevision(value => value + 1)}>↻ 이력 새로고침</button>{projectRef && <button className="primary" onClick={() => onNavigate('cases')}>API 케이스 열기 →</button>}</div>
    </div>
    <div className="dashboard-filters card">
      <label className="field">프로젝트<select aria-label="프로젝트" value={projectRef} onChange={event => changeProject(event.target.value)}><option value="">전체 프로젝트</option>{projects.map(reference => <option key={reference} value={reference}>{projectDetails[reference]?.name || reference}</option>)}</select></label>
      <label className="field">조회 기간<select aria-label="조회 기간" value={days} onChange={event => { setDays(Number(event.target.value)); setPage(1) }}>{[7, 30, 90].map(value => <option key={value} value={value}>최근 {value}일</option>)}</select></label>
      <p className="hint">{updatedAt ? `${updatedAt.toLocaleTimeString('ko-KR')} 갱신` : '실행 이력 조회 중'}<br />기간·일별 집계는 UTC 기준입니다.</p>
    </div>
    {error && <div className="dashboard-error" role="alert">{error} <button onClick={() => setRevision(value => value + 1)}>다시 시도</button>{data && <span>마지막으로 조회한 데이터를 표시합니다.</span>}</div>}
    {!data && !error && <div className="empty" role="status">실행 이력을 불러오는 중입니다…</div>}
    {data && <>
      <div className="dashboard-metrics">
        <article className="card"><span>전체 실행</span><strong>{count(summary.total)}<small>회</small></strong><p>선택한 기간에 시작하고 완료된 실행</p></article>
        <article className="card"><span>성공률</span><strong className="dashboard-positive">{summary.successRate == null ? '—' : `${summary.successRate}%`}</strong><p>성공 {count(summary.passed)}회 / 전체 {count(summary.total)}회</p></article>
        <article className="card"><span>실패·오류</span><strong className="dashboard-negative">{count(summary.failed + summary.error + summary.timeout)}<small>회</small></strong><p>실패 {count(summary.failed)} · 오류 {count(summary.error)} · 시간 초과 {count(summary.timeout)}</p></article>
        <article className="card"><span>평균 실행 소요 시간</span><strong>{duration(summary.averageDurationMs)}</strong><p>파이프라인 전체 처리 시간 포함</p></article>
      </div>
      <section className="card dashboard-trend">
        <div className="section-header"><h2>일별 실행 추이</h2><div className="dashboard-legend"><span>● 성공</span><span>● 실패·오류</span></div></div>
        {summary.total === 0 ? <div className="empty">선택한 기간에 완료된 실행이 없습니다. API 케이스 또는 파이프라인을 실행하면 여기에 표시됩니다.</div> : <div className="dashboard-chart-scroll"><div className="dashboard-chart" style={{ minWidth: days * 23 }} role="list" aria-label="UTC 기준 일별 실행 횟수">
          {data.trend.map((day, index) => <div key={day.date} className="dashboard-day" role="listitem" tabIndex={0} aria-label={`${day.date}: 전체 ${day.total}회, 성공 ${day.passed}회, 실패·오류 ${day.failed}회`} title={`${day.date} · 성공 ${day.passed} · 실패·오류 ${day.failed}`}>
            <div className="dashboard-bar"><div className="dashboard-bar-failed" style={{ height: `${day.failed / maximum * 100}%` }} /><div className="dashboard-bar-passed" style={{ height: `${day.passed / maximum * 100}%` }} /></div>
            <span>{days === 7 || index % (days === 30 ? 5 : 15) === 0 || index === days - 1 ? day.date.slice(5).replace('-', '/') : ' '}</span>
          </div>)}
        </div></div>}
        <p className="hint">케이스 여러 개 또는 파이프라인을 함께 요청한 경우 한 번의 실행으로 집계합니다. 막대에 마우스를 올리거나 키보드로 이동하면 횟수를 확인할 수 있습니다.</p>
      </section>
      <section className="card dashboard-history">
        <div className="section-header"><div><h2>최근 실행 이력</h2><p className="hint">{count(data.total)}건 · 결과 필터는 이력 목록에 적용됩니다.</p></div><label className="field">실행 결과<select aria-label="실행 결과" value={status} onChange={event => { setStatus(event.target.value); setPage(1) }}><option value="">전체 결과</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
        {data.items.length === 0 ? <div className="empty">조회 조건에 맞는 실행 이력이 없습니다.</div> : <div className="dashboard-table-scroll"><table><thead><tr><th>실행 시각</th><th>실행 대상</th><th>프로젝트</th><th>결과</th><th>소요 시간</th></tr></thead><tbody>{data.items.map(item => <tr key={item.id}>
          <td><time dateTime={item.startedAt}>{new Date(item.startedAt).toLocaleString('ko-KR')}</time></td>
          <td><details><summary>{item.targets[0]?.reference || '전체 파이프라인'}{item.targets.length > 1 ? ` 외 ${item.targets.length - 1}개` : ''}</summary><ul>{item.targets.map((target, index) => <li key={index}>{target.kind === 'case' ? '케이스' : '파이프라인'} · {target.reference}{target.preview ? ' (저장 전 내용 실행)' : ''}</li>)}</ul><p>종료 코드: {item.exitCode ?? '없음'}</p></details></td>
          <td>{item.projects.map(reference => projectDetails[reference]?.name || reference).join(', ') || '프로젝트 미지정'}</td>
          <td><span className={`dashboard-status ${item.status}`}>{statusLabels[item.status]}</span></td><td>{duration(item.durationMs)}</td>
        </tr>)}</tbody></table></div>}
        <div className="dashboard-pagination"><button disabled={page <= 1} onClick={() => setPage(value => value - 1)}>이전</button><span>{page} / {totalPages}</span><button disabled={page >= totalPages} onClick={() => setPage(value => value + 1)}>다음</button></div>
      </section>
      <p className="hint">대시보드 도입 이후 웹에서 실행한 이력을 표시합니다. 요청·응답 본문과 인증 정보는 대시보드 이력에 저장하지 않습니다.</p>
    </>}
  </main>
}
