import { useState } from 'react'
import { Field } from '../../components/Field.jsx'
import { api } from '../../utils/studio.js'

export function OperationEditor({ operation, projectRef, project, onSaved, onCancel }) {
  const original = operation.editable || {}
  const [changes, setChanges] = useState({})
  const [preview, setPreview] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const value = key => changes[key] ?? original[key] ?? (key === 'tags' ? [] : key === 'deprecated' ? false : '')
  const change = (key, next) => { setChanges(current => ({ ...current, [key]: next })); setPreview(null); setError('') }
  const save = async () => {
    setSaving(true); setError('')
    try {
      await api(`/api/projects/${encodeURIComponent(projectRef)}/openapi/operations`, {
        method: 'POST', body: JSON.stringify({ action: preview, method: operation.method, path: operation.path, changes, _storage: project._storage }),
      })
      await onSaved()
    } catch (requestError) { setError(requestError.message) }
    finally { setSaving(false) }
  }
  return <section className="card" aria-label="Operation 편집">
    <h2>{operation.method} {operation.path} 편집</h2>
    <p className="hint">설명과 식별자를 수정합니다. 요청·응답·인증·schema는 보존됩니다.</p>
    {project.docs_url && <p className="notice">저장하면 원격 문서의 프로젝트 사본이 생성됩니다.</p>}
    <fieldset disabled={saving} style={{ border: 0, padding: 0 }}>
      <div className="form-grid">
        {['operationId', 'summary', 'description'].map(key => <Field key={key} label={key}><input aria-label={key} value={value(key)} onChange={event => change(key, event.target.value)} /></Field>)}
        <Field label="tags (쉼표 구분)"><input aria-label="tags" value={value('tags').join(', ')} onChange={event => change('tags', event.target.value === '' ? [] : event.target.value.split(',').map(tag => tag.trim()))} /></Field>
        <label className="toggle"><input type="checkbox" checked={value('deprecated')} onChange={event => change('deprecated', event.target.checked)} />deprecated</label>
      </div>
      <div className="actions">
        <button className="ghost" onClick={onCancel}>닫기</button>
        <button className="ghost" disabled={!Object.keys(changes).length} onClick={() => setPreview('update')}>변경 미리보기</button>
        <button className="danger" onClick={() => setPreview('delete')}>Operation 삭제</button>
      </div>
      {preview && <div role="region" aria-label="변경 미리보기">
        {preview === 'delete' ? <p>이 operation을 삭제합니다. 연결된 테스트 케이스는 유지됩니다.</p> : <pre>{JSON.stringify({ before: Object.fromEntries(Object.keys(changes).map(key => [key, original[key] ?? null])), after: changes }, null, 2)}</pre>}
        <button className="primary" onClick={save}>{saving ? '저장 중…' : preview === 'delete' ? '삭제 확정' : '변경 저장'}</button>
      </div>}
    </fieldset>
    {error && <p role="alert" className="notice">{error}</p>}
  </section>
}
