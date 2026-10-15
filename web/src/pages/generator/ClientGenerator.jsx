import { authenticatedFetch } from '../../auth/session.js'
import { Field } from '../../components/Field.jsx'
import { AuthorSidebar } from '../../components/ProjectSidebar.jsx'
import { useRunJob } from '../../hooks/useRunJob.js'
import { useEffect, useRef, useState } from 'react'

const clientLanguages = [
  ['python', 'Python'], ['javascript', 'JavaScript'], ['typescript', 'TypeScript (Axios)'],
  ['java', 'Java'], ['kotlin', 'Kotlin'], ['go', 'Go'], ['csharp', 'C#'],
]

const statusLabel = {
  queued: '대기 중', running: '생성 중', cancelling: '취소 중', reconnecting: '작업 다시 조회 중',
  passed: '생성 완료', failed: '생성 실패', error: '생성 오류', timeout: '시간 초과', cancelled: '취소됨',
}

function GenerationJobPanel({ projectRef, project, language, hasDocument }) {
  const { result, busy, start, cancel } = useRunJob(`sdk:${projectRef}:${language}`)
  const [submitting, setSubmitting] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const [notice, setNotice] = useState('')
  const downloadController = useRef(null)
  useEffect(() => () => downloadController.current?.abort(), [])
  const revision = project?._storage?.revision
  const canSubmit = Boolean(projectRef && hasDocument && Number.isInteger(revision) && revision > 0)
  const generate = async () => {
    setSubmitting(true); setNotice(''); setDownloadError('')
    try {
      await start({ project: projectRef, language, projectRevision: revision }, '/api/generations')
    } catch { /* useRunJob displays the rejected submission without retrying. */ }
    finally { setSubmitting(false) }
  }
  const download = async () => {
    if (result?.status !== 'passed' || !result?.generation?.artifactReady || !result.runId) return
    const controller = new AbortController()
    downloadController.current = controller
    setDownloading(true); setDownloadError(''); setNotice('')
    try {
      const response = await authenticatedFetch(`/api/generations/${encodeURIComponent(result.runId)}/artifact`, { signal: controller.signal })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(response.status === 404 ? '다운로드 파일이 만료되었거나 없습니다. 다시 생성하세요.' : data.error || '다운로드에 실패했습니다.')
      }
      const blob = await response.blob()
      if (controller.signal.aborted) return
      const disposition = response.headers.get('Content-Disposition') || ''
      const fallback = `${projectRef.replace(/[^A-Za-z0-9_-]/g, '_')}-${language}-client.zip`
      const filename = disposition.match(/filename="([^"]+)"/)?.[1] || fallback
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
      setNotice(`${filename} 다운로드를 시작했습니다.`)
    } catch (error) { if (error.name !== 'AbortError') setDownloadError(error.message) }
    finally { if (downloadController.current === controller) { downloadController.current = null; setDownloading(false) } }
  }
  const status = result?.status
  const generation = result?.generation
  const canCancel = Boolean(result?.runId && ['queued', 'running'].includes(status))
  return <div className="generator-job">
    <div className="generator-actions">
      <button className="primary" disabled={!canSubmit || busy || submitting} onClick={generate}>{submitting ? '제출 중…' : 'SDK 생성 작업 제출'}</button>
      {canCancel && <button className="ghost" onClick={cancel}>작업 취소</button>}
    </div>
    {!hasDocument && <p className="generator-warning">API 목록에서 API를 작성하거나 프로젝트 설정에서 OpenAPI 문서를 등록하세요.</p>}
    {hasDocument && !revision && <p className="generator-warning">프로젝트 revision을 불러온 뒤 생성할 수 있습니다.</p>}
    {result && <section className="generator-job-status" aria-label="SDK 생성 작업 상태" aria-live="polite">
      <strong>{statusLabel[status] || (result.error ? '작업 확인 필요' : status || '상태 확인 중')}</strong>
      {result.runId && <p>작업 ID <code>{result.runId}</code></p>}
      {generation && <><p>요청 당시 프로젝트 revision: {generation.projectRevision}</p><p>원본 지문: {generation.sourceDigest || '원본 확인 중'}</p>{generation.fetchedAt && <p>URL 원본 확인: {new Date(generation.fetchedAt).toLocaleString('ko-KR')}</p>}{generation.artifact?.expiresAt && <p>ZIP 보관 기한: {new Date(generation.artifact.expiresAt).toLocaleString('ko-KR')}</p>}</>}
      {result.pollError && <p role="status">{result.pollError}</p>}
      {result.error && <p role="alert">{result.error}</p>}
      {status === 'passed' && generation?.artifactReady && <button className="primary" disabled={downloading} onClick={download}>{downloading ? '다운로드 중…' : 'ZIP 다운로드'}</button>}
      {status === 'passed' && !generation?.artifactReady && <p className="generator-warning">다운로드 파일을 사용할 수 없습니다. 다시 생성하세요.</p>}
      {['failed', 'error', 'timeout', 'cancelled'].includes(status) && !result.error && <p className="hint">작업이 완료되지 않았습니다. 필요하면 새 생성 작업을 제출하세요.</p>}
    </section>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {downloadError && <p className="notice" role="alert">{downloadError}</p>}
  </div>
}

function ProjectClientGenerator({ projects, projectRef, project, onProjectChange, onNavigate, onProjectList }) {
  const languageKey = `studio-sdk-language:${projectRef}`
  const [language, setLanguage] = useState(() => {
    try {
      const saved = sessionStorage.getItem(languageKey)
      return clientLanguages.some(([value]) => value === saved) ? saved : 'typescript'
    } catch { return 'typescript' }
  })
  const selectLanguage = value => {
    setLanguage(value)
    try { sessionStorage.setItem(languageKey, value) } catch { /* Storage may be unavailable. */ }
  }
  const hasDocument = Boolean(project?.docs_bundle || project?.docs_url || project?.docs_file?.document)
  const documentLabel = project?.docs_bundle?.entrypoint ? `${project.docs_bundle.entrypoint} · ${Object.keys(project.docs_bundle.files || {}).length}개 파일` : project?.docs_url || project?.docs_file?.name || '등록된 OpenAPI 문서 없음'
  return <div className="workspace"><AuthorSidebar active="generator" projects={projects} projectRef={projectRef} project={project} onProjectChange={onProjectChange} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card generator-card"><div className="section-header"><div><p className="eyebrow">OPENAPI CLIENT GENERATOR</p><h2>OpenAPI 기반 SDK 생성</h2></div></div><p className="hint">프로젝트에 등록한 OpenAPI 문서로 선택한 언어의 API 클라이언트를 생성합니다. 작업 완료 후 ZIP을 직접 다운로드할 수 있습니다.</p><div className="generator-source"><span>문서 원본</span><code>{documentLabel}</code></div><div className="generator-controls"><Field label="생성 언어"><select value={language} onChange={event => selectLanguage(event.target.value)}>{clientLanguages.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field></div><GenerationJobPanel key={`${projectRef}:${language}`} projectRef={projectRef} project={project} language={language} hasDocument={hasDocument} /></section></main></div>
}

function ClientGenerator(props) {
  return <ProjectClientGenerator key={props.projectRef} {...props} />
}

export { ClientGenerator }
