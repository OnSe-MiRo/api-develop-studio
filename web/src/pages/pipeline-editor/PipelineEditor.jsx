import { Field } from '../../components/Field.jsx'
import { RunResult } from '../../components/RunResult.jsx'
import { TestSidebar } from '../../components/ProjectSidebar.jsx'
import { jsonFileName, api } from '../../utils/studio.js'
import { useEffect, useState } from 'react'

const newMappingDraft = () => ({ source_step: '', response_path: 'body.id', target: 'body', target_key: '', template: '{{value}}' })

function ValueMappingEditor({ editor, steps, onUpdateDraft, onAdd, onRemove, onSave, onCancel }) {
  const sourceSteps = steps.slice(0, editor.index)
  const draft = editor.draft
  const targetLabel = mapping => ({ url: 'URL', header: `Header: ${mapping.target_key}`, body: `Body: ${mapping.target_key}` }[mapping.target])
  return <section className="card mapping-card"><div className="section-header"><div><p className="eyebrow">VALUE TRANSFER</p><h2>{steps[editor.index]?.name} 요청에 값 전달</h2></div><div className="actions"><button className="ghost" onClick={onCancel}>닫기</button><button className="primary" onClick={onSave}>적용</button></div></div>{sourceSteps.length ? <><div className="mapping-grid"><Field label="A 단계"><select value={draft.source_step} onChange={event => onUpdateDraft('source_step', event.target.value)}><option value="">이전 단계 선택</option>{sourceSteps.map(step => <option key={step.name} value={step.name}>{step.name}</option>)}</select></Field><Field label="A 응답 경로"><input value={draft.response_path} onChange={event => onUpdateDraft('response_path', event.target.value)} placeholder="body.id 또는 status" /></Field><Field label="B 적용 위치"><select value={draft.target} onChange={event => onUpdateDraft('target', event.target.value)}><option value="url">Request URL</option><option value="header">Request Header</option><option value="body">Request Body</option></select></Field>{draft.target !== 'url' && <Field label="B 대상 키"><input value={draft.target_key} onChange={event => onUpdateDraft('target_key', event.target.value)} placeholder={draft.target === 'header' ? 'X-User-Id' : 'user.id'} /></Field>}<Field label="B 값 템플릿"><input value={draft.template} onChange={event => onUpdateDraft('template', event.target.value)} placeholder="/users/{{value}} 또는 Bearer {{value}}" /></Field></div><div className="step-actions"><p className="hint">A 값이 들어갈 위치에 <code>{'{{value}}'}</code>를 넣으세요. 예: <code>/users/{'{{value}}'}</code></p><button className="primary" onClick={onAdd}>＋ 값 전달 추가</button></div><div className="mapping-list">{editor.mappings.length ? editor.mappings.map((mapping, index) => <div className="mapping-item" key={`${mapping.source_step}-${mapping.response_path}-${index}`}><div><strong>{mapping.source_step}.response.{mapping.response_path}</strong><small>{targetLabel(mapping)} · {mapping.template}</small></div><button className="icon danger" title="값 전달 삭제" onClick={() => onRemove(index)}>×</button></div>) : <div className="empty">등록된 값 전달 설정이 없습니다.</div>}</div></> : <div className="empty">값을 전달할 이전 단계를 먼저 추가하세요.</div>}</section>
}

function PipelineEditor({ caseItems, refresh, projectRef, project, onNavigate, onProjectList, pipelineReference, onBack }) {
  const [fileName, setFileName] = useState('new_pipeline.json')
  const [defaults, setDefaults] = useState({ retry: 0, retry_interval_seconds: 0 })
  const [steps, setSteps] = useState([])
  const [draft, setDraft] = useState({ name: '', case: '', retry: '', interval: '', continue: false })
  const [selected, setSelected] = useState('')
  const [notice, setNotice] = useState('')
  const [result, setResult] = useState(null)
  const [mappingEditor, setMappingEditor] = useState(null)
  const [storageMeta, setStorageMeta] = useState(null)
  const ref = jsonFileName(fileName)
  useEffect(() => { if (!draft.case && caseItems.length) setDraft(current => ({ ...current, case: caseItems[0] })) }, [caseItems])
  useEffect(() => {
    setResult(null)
    if (pipelineReference) load(pipelineReference)
    else { setFileName('new_pipeline.json'); setDefaults({ retry: 0, retry_interval_seconds: 0 }); setSteps([]); setDraft({ name: '', case: '', retry: '', interval: '', continue: false }); setMappingEditor(null); setSelected(''); setStorageMeta(null); setNotice('새 파이프라인을 작성하세요.') }
  }, [pipelineReference, projectRef])
  const load = async reference => {
    if (!reference) return
    try { const data = await api(`/api/pipelines/${encodeURIComponent(reference)}`); setFileName(reference); setDefaults(data.defaults || { retry: 0, retry_interval_seconds: 0 }); setSteps(data.steps || []); setMappingEditor(null); setSelected(reference); setStorageMeta(data._storage || null); setNotice(`불러옴: ${reference}`); setResult(null) } catch (error) { setNotice(error.message) }
  }
  const addStep = () => {
    if (!draft.name || !draft.case) return setNotice('단계 이름과 케이스를 선택하세요.')
    if (steps.some(step => step.name === draft.name)) return setNotice('단계 이름은 고유해야 합니다.')
    const step = { name: draft.name, case: draft.case }
    if (draft.external) { step.phase = 'setup'; step.external_once = true; step.retry = 0; step.retry_interval_seconds = 0 }
    if (!draft.external && draft.retry !== '') step.retry = Number(draft.retry)
    if (!draft.external && draft.interval !== '') step.retry_interval_seconds = Number(draft.interval)
    if (!draft.external && draft.continue) step.continue_on_failure = true
    setSteps(current => draft.external ? [...current.filter(s => s.phase === 'setup'), step, ...current.filter(s => s.phase !== 'setup')] : [...current, step]); setDraft(current => ({ ...current, name: '', retry: '', interval: '', continue: false }))
  }
  const pipelineDocument = () => {
    if (!projectRef) throw new Error('프로젝트를 먼저 선택하세요.')
    if (!steps.length) throw new Error('최소 한 개의 단계를 추가하세요.')
    return { project: projectRef, defaults: { retry: Number(defaults.retry), retry_interval_seconds: Number(defaults.retry_interval_seconds) }, steps }
  }
  const save = async () => {
    try { const payload = pipelineDocument(); const saved = await api(`/api/pipelines/${encodeURIComponent(ref)}`, { method: 'PUT', body: JSON.stringify(selected === ref && storageMeta ? { ...payload, _storage: storageMeta } : payload) }); setStorageMeta(saved._storage || null); await refresh(); setSelected(ref); setNotice(`저장됨: pipelines/${ref}`); return true } catch (error) { setNotice(error.message); return false }
  }
  const runOnly = async () => {
    try {
      setResult(null); setNotice('현재 파이프라인을 저장하지 않고 실행 중입니다.')
      setResult(await api('/api/run', { method: 'POST', body: JSON.stringify({ inlinePipeline: pipelineDocument() }) }))
      setNotice('저장하지 않고 실행했습니다.')
    } catch (error) { setResult({ error: error.message }); setNotice(error.message) }
  }
  const run = async () => { if (!(await save())) return; try { setResult(await api('/api/run', { method: 'POST', body: JSON.stringify({ pipelines: [ref] }) })) } catch (error) { setResult({ error: error.message }) } }
  const removePipeline = async () => {
    if (!selected) return setNotice('삭제할 저장된 파이프라인을 먼저 선택하세요.')
    if (!window.confirm(`${selected} 파이프라인을 삭제할까요?\n목록과 실행 파일에서는 제거되지만 변경 이력은 보관됩니다.`)) return
    try {
      await api(`/api/pipelines/${encodeURIComponent(selected)}`, { method: 'DELETE' })
      await refresh(); setFileName('new_pipeline.json'); setSteps([]); setMappingEditor(null); setSelected(''); setStorageMeta(null); setResult(null); setNotice(`삭제됨: pipelines/${selected}`)
    } catch (error) { setNotice(error.message) }
  }
  const move = (index, offset) => { setMappingEditor(null); setSteps(current => { const target = index + offset; if (target < 0 || target >= current.length) return current; const next = [...current];[next[index], next[target]] = [next[target], next[index]]; return next }) }
  const openMappings = index => setMappingEditor({ index, mappings: steps[index].input_mappings || [], draft: newMappingDraft() })
  const updateMappingDraft = (key, value) => setMappingEditor(current => current ? { ...current, draft: { ...current.draft, [key]: value } } : current)
  const addMapping = () => {
    if (!mappingEditor) return
    const mapping = mappingEditor.draft
    const sourceSteps = steps.slice(0, mappingEditor.index)
    if (!sourceSteps.some(step => step.name === mapping.source_step)) return setNotice('값을 가져올 이전 단계를 선택하세요.')
    if (!/^(body(?:\.[\w-]+)*|status)$/.test(mapping.response_path)) return setNotice('응답 경로는 body.id 또는 status 형식이어야 합니다.')
    if (!mapping.template.includes('{{value}}')) return setNotice('값 템플릿에 {{value}}를 포함하세요.')
    if (mapping.target !== 'url' && !/^[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*$/.test(mapping.target_key)) return setNotice('Header 또는 Body 대상 키를 입력하세요.')
    const next = { source_step: mapping.source_step, response_path: mapping.response_path, target: mapping.target, template: mapping.template }
    if (mapping.target !== 'url') next.target_key = mapping.target_key
    setMappingEditor(current => current ? { ...current, mappings: [...current.mappings, next], draft: newMappingDraft() } : current)
  }
  const saveMappings = () => {
    if (!mappingEditor) return
    setSteps(current => current.map((step, index) => {
      if (index !== mappingEditor.index) return step
      const { input_mappings, ...withoutMappings } = step
      return mappingEditor.mappings.length ? { ...withoutMappings, input_mappings: mappingEditor.mappings } : withoutMappings
    }))
    setMappingEditor(null); setNotice('값 전달 설정을 적용했습니다.')
  }
  return <div className="workspace"><TestSidebar active="pipeline" projectRef={projectRef} project={project} onNavigate={onNavigate} onProjectList={onProjectList} /><main className="editor"><section className="card"><div className="section-header"><div><p className="eyebrow">PIPELINE SETTINGS</p><h2>{selected ? '파이프라인 설정' : '새 파이프라인'}</h2></div><div className="actions"><button className="ghost" onClick={onBack}>목록으로</button>{selected && <button className="danger-button" onClick={removePipeline}>삭제</button>}<button className="ghost" onClick={save}>저장</button><button className="ghost" onClick={runOnly}>실행만</button><button className="primary" onClick={run}>저장 후 실행</button></div></div><div className="form-grid three"><Field label="파일명"><input value={fileName} onChange={event => setFileName(event.target.value)} /></Field><Field label="기본 재시도"><input type="number" min="0" value={defaults.retry} onChange={event => setDefaults(current => ({ ...current, retry: event.target.value }))} /></Field><Field label="기본 간격 (초)"><input type="number" min="0" step="0.1" value={defaults.retry_interval_seconds} onChange={event => setDefaults(current => ({ ...current, retry_interval_seconds: event.target.value }))} /></Field></div></section><section className="card"><div className="section-header"><div><p className="eyebrow">ADD STEP</p><h2>테스트 단계 추가</h2></div></div><div className="form-grid step-grid"><Field label="케이스" wide><select value={draft.case} onChange={event => setDraft(current => ({ ...current, case: event.target.value }))} disabled={!projectRef}>{caseItems.map(item => <option key={item}>{item}</option>)}</select></Field><Field label="단계 이름"><input value={draft.name} onChange={event => setDraft(current => ({ ...current, name: event.target.value }))} placeholder="get_user" /></Field><Field label="재시도 (선택)"><input type="number" min="0" value={draft.retry} onChange={event => setDraft(current => ({ ...current, retry: event.target.value }))} /></Field><Field label="간격 (선택)"><input type="number" min="0" step="0.1" value={draft.interval} onChange={event => setDraft(current => ({ ...current, interval: event.target.value }))} /></Field></div><div className="step-actions"><label className="toggle"><input type="checkbox" checked={Boolean(draft.external)} onChange={event => setDraft(current => ({ ...current, external: event.target.checked, retry: event.target.checked ? '0' : '', continue: false }))} /><span>Setup · 승인된 외부 API 1회 호출</span></label><label className="toggle"><input type="checkbox" checked={draft.continue} onChange={event => setDraft(current => ({ ...current, continue: event.target.checked }))} /><span>실패해도 다음 단계 실행</span></label><button className="primary" onClick={addStep}>＋ 단계 추가</button></div></section><section className="card"><div className="section-header"><div><p className="eyebrow">EXECUTION ORDER</p><h2>실행 순서 <span className="count">{steps.length}</span></h2></div></div><div className="steps">{steps.length ? steps.map((step, index) => <div className="step" key={step.name}><span className="order">{String(index + 1).padStart(2, '0')}</span><div><strong>{step.external_once ? 'Setup · 외부 1회 · ' : ''}{step.name}</strong><small>{step.case}{step.input_mappings?.length ? ` · 값 전달 ${step.input_mappings.length}개` : ''}</small></div><div className="step-meta">재시도 {step.retry ?? '기본값'} · 간격 {step.retry_interval_seconds ?? '기본값'}</div><div className="row-actions"><button className="mapping-button" onClick={() => openMappings(index)}>값 전달</button><button className="icon" onClick={() => move(index, -1)}>↑</button><button className="icon" onClick={() => move(index, 1)}>↓</button><button className="icon danger" onClick={() => setSteps(current => current.filter((_, itemIndex) => itemIndex !== index))}>×</button></div></div>) : <div className="empty">API 케이스를 먼저 저장한 뒤 단계로 추가하세요.</div>}</div></section>{mappingEditor && <ValueMappingEditor editor={mappingEditor} steps={steps} onUpdateDraft={updateMappingDraft} onAdd={addMapping} onRemove={index => setMappingEditor(current => current ? { ...current, mappings: current.mappings.filter((_, itemIndex) => itemIndex !== index) } : current)} onSave={saveMappings} onCancel={() => setMappingEditor(null)} />}{notice && <p className="notice">{notice}</p>}<RunResult result={result} onClose={() => setResult(null)} /></main></div>
}

export { PipelineEditor }
