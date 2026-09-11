import { AuthorSidebar } from '../../components/ProjectSidebar.jsx'
import { asText, docValue, groupDocOperationsByTag, api } from '../../utils/studio.js'
import { useEffect, useState } from 'react'

function SwaggerOperation({ operation }) {
  const [expanded, setExpanded] = useState(false)
  const responses = operation.responses?.length ? operation.responses : [{ status: operation.expected_status, description: '', has_body: operation.has_response_body, body: operation.response_body }]
  return <article className={`swagger-operation method-${operation.method.toLowerCase()} ${expanded ? 'expanded' : ''}`}><button className="swagger-summary" onClick={() => setExpanded(current => !current)} aria-expanded={expanded}><span className="swagger-method">{operation.method}</span><code>{operation.path}</code><strong>{operation.summary || '설명 없음'}</strong><span className="swagger-tag">{operation.tag || 'default'}</span><span className="swagger-expand">{expanded ? '−' : '+'}</span></button>{expanded && <div className="swagger-details">{operation.parameters?.length > 0 && <section><h4>Parameters</h4><div className="swagger-parameters">{operation.parameters.map(parameter => <div key={`${parameter.in}-${parameter.name}`}><code>{parameter.name}</code><span>{parameter.in}</span><small>{docValue(parameter.value) || '예시 없음'}</small></div>)}</div></section>}{operation.has_request_body && <section><h4>Request body <span>application/json</span></h4><pre>{JSON.stringify(operation.request_body, null, 2)}</pre></section>}<section><h4>Responses</h4><div className="swagger-responses">{responses.map(response => <div className="swagger-response" key={response.status}><div className="swagger-response-status"><strong>{response.status}</strong><span>{response.description || 'application/json'}</span></div>{response.has_body && <pre>{JSON.stringify(response.body, null, 2)}</pre>}</div>)}</div></section></div>}</article>
}

function ApiList({ projects, projectRef, project, onProjectChange, onNavigate, onProjectList, onCreate }) {
  const [operations, setOperations] = useState([])
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const bundle = project?.docs_bundle
      const document = project?.docs_file?.document
      const url = asText(project?.docs_url).trim()
      if (!bundle && !document && !url) { setOperations([]); setNotice('작성된 API가 없습니다. 새 API를 작성하면 OpenAPI 문서가 자동 생성됩니다.'); return }
      try {
        const request = bundle ? { bundle } : document ? { document } : { url, no_proxy: project?.advanced?.use_proxy === false }
        const data = await api('/api/docs', { method: 'POST', body: JSON.stringify(request) })
        if (!cancelled) { setOperations(data.operations || []); setNotice('') }
      } catch (error) { if (!cancelled) { setOperations([]); setNotice(error.message) } }
    }
    load()
    return () => { cancelled = true }
  }, [projectRef, project?.docs_url, project?._storage?.revision])
  return <div className="workspace"><AuthorSidebar active="apis" projects={projects} projectRef={projectRef} project={project} onProjectChange={onProjectChange} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">OPENAPI AUTHORING</p><h2>API 목록 <span className="count">{operations.length}</span></h2></div><button className="primary" disabled={!projectRef} onClick={onCreate}>＋ API 작성</button></div>{operations.length ? <div className="swagger-list">{groupDocOperationsByTag(operations).map(([tag, items]) => <section className="swagger-tag-group" key={tag}><h3>{tag} <span>{items.length}</span></h3>{items.map(operation => <SwaggerOperation key={operation.id} operation={operation} />)}</section>)}</div> : <div className="empty">표시할 API가 없습니다.</div>}</section>{notice && <p className="notice" role="status">{notice}</p>}</main></div>
}

export { ApiList }
