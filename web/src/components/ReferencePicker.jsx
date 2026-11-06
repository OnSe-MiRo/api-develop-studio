import { useEffect, useState } from 'react'
import { api } from '../utils/studio.js'

const empty = { items: [], details: {} }

export function useReferencePage(resource, project, search, cursor, revision = 0) {
  const query = new URLSearchParams({ page_size: '20' })
  if (project) query.set('project', project)
  if (search) query.set('q', search)
  if (cursor) query.set('cursor', cursor)
  const url = resource === 'cases' && !project ? '' : `/api/${resource}?${query}`
  const [state, setState] = useState({})
  useEffect(() => {
    if (!url) return
    const controller = new AbortController()
    api(url, { signal: controller.signal }).then(page => {
      if (!Array.isArray(page?.items) || page.items.some(item => typeof item !== 'string')) throw new Error('선택지 목록을 읽을 수 없습니다.')
      if (!controller.signal.aborted) setState({ url, revision, page })
    }).catch(error => {
      if (!controller.signal.aborted) setState({ url, revision, error: error.message })
    })
    return () => controller.abort()
  }, [url, revision])
  if (!url) return { page: empty }
  if (url !== state.url || revision !== state.revision) return { page: empty, loading: true }
  return { ...state, page: state.page || empty }
}

export function ReferencePicker({ resource, project, label, value, onChange, placeholder, selectFirst = false, onPage, disabled = false, refreshKey = 0 }) {
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const [cursor, setCursor] = useState('')
  const [retry, setRetry] = useState(0)
  const { page, loading, error } = useReferencePage(resource, project, search, cursor, `${refreshKey}:${retry}`)
  useEffect(() => { if (page.details) onPage?.(page.details) }, [page, onPage])
  const items = page.items
  useEffect(() => {
    if (selectFirst && !value && items.length) onChange(items[0])
  }, [selectFirst, value, items, onChange])
  const options = value && !items.includes(value) ? [value, ...items] : items
  const apply = () => { setSearch(draft.trim()); setCursor('') }
  return <div className="reference-picker">
    <label className="field"><span>{label}</span><select aria-label={label} value={value} disabled={disabled || loading} onChange={event => onChange(event.target.value)}>
      <option value="">{placeholder}</option>
      {options.map(ref => <option key={ref} value={ref}>{page.details?.[ref]?.name || ref}</option>)}
    </select></label>
    {(search || draft || cursor || page.nextCursor || page.previousCursor) && <div className="actions">
      <input aria-label={label + ' 선택지 검색어'} placeholder="이름 또는 경로 검색" value={draft} maxLength={100} onChange={e => setDraft(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); apply() } }} />
      <button type="button" disabled={disabled} onClick={apply}>선택지 검색</button>
      <button type="button" aria-label={label + ' 이전 선택지'} disabled={disabled || loading || !page.previousCursor} onClick={() => setCursor(page.previousCursor)}>이전</button>
      <button type="button" aria-label={label + ' 다음 선택지'} disabled={disabled || loading || !page.nextCursor} onClick={() => setCursor(page.nextCursor)}>다음</button>
    </div>}
    {error && <div role="alert">{error} <button type="button" onClick={() => { setCursor(''); setRetry(n => n + 1) }}>선택지 다시 조회</button></div>}
  </div>
}
