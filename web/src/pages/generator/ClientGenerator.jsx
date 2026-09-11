import { Field } from '../../components/Field.jsx'
import { AuthorSidebar } from '../../components/ProjectSidebar.jsx'
import { useState } from 'react'

const clientLanguages = [
  ['python', 'Python'], ['javascript', 'JavaScript'], ['typescript', 'TypeScript (Axios)'],
  ['java', 'Java'], ['kotlin', 'Kotlin'], ['go', 'Go'], ['csharp', 'C#'],
]

function ClientGenerator({ projects, projectRef, project, onProjectChange, onNavigate, onProjectList }) {
  const [language, setLanguage] = useState('typescript')
  const [generating, setGenerating] = useState(false)
  const [notice, setNotice] = useState('')
  const hasDocument = Boolean(project?.docs_bundle || project?.docs_url || project?.docs_file?.document)
  const documentLabel = project?.docs_bundle?.entrypoint ? `${project.docs_bundle.entrypoint} · ${Object.keys(project.docs_bundle.files || {}).length}개 파일` : project?.docs_url || project?.docs_file?.name || '등록된 OpenAPI 문서 없음'
  const generate = async () => {
    setGenerating(true); setNotice('OpenAPI 문서를 분석해 SDK를 생성하는 중입니다.')
    try {
      const response = await fetch('/api/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project: projectRef, language }),
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.error || 'SDK 생성에 실패했습니다.')
      }
      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition') || ''
      const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `${projectRef.replace(/\.json$/, '')}-${language}-client.zip`
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
      setNotice(`${filename} 다운로드를 시작했습니다.`)
    } catch (error) { setNotice(error.message) }
    finally { setGenerating(false) }
  }
  return <div className="workspace"><AuthorSidebar active="generator" projects={projects} projectRef={projectRef} project={project} onProjectChange={onProjectChange} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card generator-card"><div className="section-header"><div><p className="eyebrow">OPENAPI CLIENT GENERATOR</p><h2>OpenAPI 기반 SDK 생성</h2></div></div><p className="hint">프로젝트에 등록한 OpenAPI 문서를 기준으로 선택한 언어의 API 클라이언트를 생성합니다. ZIP에는 생성 코드와 정규화된 <code>openapi.yaml</code>이 함께 포함됩니다.</p><div className="generator-source"><span>문서 원본</span><code>{documentLabel}</code></div><div className="generator-controls"><Field label="생성 언어"><select value={language} onChange={event => setLanguage(event.target.value)}>{clientLanguages.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field><button className="primary" disabled={!hasDocument || generating} onClick={generate}>{generating ? '생성 중…' : 'ZIP 생성 및 다운로드'}</button></div>{!hasDocument && <p className="generator-warning">API 목록에서 API를 작성하거나 프로젝트 설정에서 OpenAPI 문서를 등록하세요.</p>}</section>{notice && <p className="notice" role="status" aria-live="polite">{notice}</p>}</main></div>
}

export { ClientGenerator }
