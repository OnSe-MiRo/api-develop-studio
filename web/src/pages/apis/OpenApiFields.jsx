import { useEffect, useState } from 'react'
import { Field } from '../../components/Field.jsx'
import { JsonArea } from '../../components/JsonArea.jsx'
import { clone, parseJsonValue } from './openapiEditorModel.js'

const schemaTypes = ['', 'string', 'integer', 'number', 'boolean', 'object', 'array']
const text = value => value === undefined ? '' : String(value)
const json = value => value === undefined ? '' : JSON.stringify(value, null, 2)
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const schemaShape = value => typeof value === 'boolean' || record(value) &&
  (value.type === undefined || typeof value.type === 'string' || Array.isArray(value.type)) &&
  (value.required === undefined || Array.isArray(value.required)) &&
  (value.properties === undefined || record(value.properties) && Object.values(value.properties).every(schemaShape)) &&
  (value.items === undefined || schemaShape(value.items))
const parameterShape = value => record(value) && (value.$ref || value.schema === undefined || schemaShape(value.schema))
const mediaShape = value => record(value) && (value.schema === undefined || schemaShape(value.schema))
const contentShape = value => record(value) && Object.values(value).every(mediaShape)
const headerShape = value => record(value) && (value.$ref || value.schema === undefined || schemaShape(value.schema))
const responseShape = value => record(value) && (value.$ref || (value.headers === undefined || record(value.headers) && Object.values(value.headers).every(headerShape)) && (value.content === undefined || contentShape(value.content)))
const requestBodyShape = value => record(value) && (value.$ref || value.content === undefined || contentShape(value.content))
const securityShape = value => Array.isArray(value) && value.every(item => record(item) && Object.values(item).every(Array.isArray))
const operationShape = value => record(value) &&
  (value.tags === undefined || Array.isArray(value.tags)) &&
  (value.parameters === undefined || Array.isArray(value.parameters) && value.parameters.every(parameterShape)) &&
  (value.requestBody === undefined || requestBodyShape(value.requestBody)) &&
  (value.responses === undefined || record(value.responses) && Object.values(value.responses).every(responseShape)) &&
  (value.security === undefined || securityShape(value.security))

function JsonValue({ label, value, onChange, onValidity, id = label, validate }) {
  const [draft, setDraft] = useState(json(value))
  const [error, setError] = useState('')
  useEffect(() => () => onValidity?.(id, true), [id])
  useEffect(() => { setDraft(current => { if (!current.trim() && value === undefined) return current; try { if (JSON.stringify(JSON.parse(current)) === JSON.stringify(value)) return current } catch { return current } return json(value) }) }, [value])
  const update = next => {
    setDraft(next)
    try { const parsed = parseJsonValue(next, label); if (validate && !validate(parsed)) throw new Error(`${label}: JSON 배열을 입력하세요.`); onChange(parsed); setError(''); onValidity?.(id, true) }
    catch (issue) { setError(issue.message); onValidity?.(id, false) }
  }
  return <Field label={`${label} JSON`} wide><JsonArea value={draft} onChange={update} placeholder={'{"id": 1}'} />{error && <small role="alert">{error}</small>}</Field>
}

function RawObject({ label, value, onChange, onValidity, id = label, allowBoolean = false, validate }) {
  const [draft, setDraft] = useState(json(value))
  const [error, setError] = useState('')
  useEffect(() => () => onValidity?.(id, true), [id])
  useEffect(() => { setDraft(current => { try { if (JSON.stringify(JSON.parse(current)) === JSON.stringify(value)) return current } catch { return current } return json(value) }) }, [value])
  const update = next => {
    setDraft(next)
    try {
      const parsed = parseJsonValue(next, label)
      if ((!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) && !(allowBoolean && typeof parsed === 'boolean')) throw new Error(`${label}: JSON 객체를 입력하세요.`)
      if (validate && !validate(parsed)) throw new Error(`${label}: 편집 가능한 OpenAPI 구조를 입력하세요.`)
      onChange(parsed); setError(''); onValidity?.(id, true)
    } catch (issue) { setError(issue.message); onValidity?.(id, false) }
  }
  return <details className="oas-raw"><summary>{label} 고급 JSON 편집</summary><p className="hint">복잡한 조합 schema와 확장 필드를 전체 객체로 편집할 수 있습니다.</p><JsonArea value={draft} onChange={update} />{error && <p role="alert">{error}</p>}</details>
}

function SchemaFields({ schema = {}, onChange, refs = [], ownerFile = '', depth = 0, version = '3.0', onValidity, id = 'schema' }) {
  const value = schema ?? {}
  if (typeof value === 'boolean') return <div className="oas-schema"><p className="hint">Boolean schema: {String(value)}</p><button className="ghost" onClick={() => onChange({ type: 'object' })}>객체 schema로 변경</button><RawObject label="Schema" value={value} onChange={onChange} onValidity={onValidity} id={id} allowBoolean validate={schemaShape} /></div>
  const set = (key, next) => {
    const updated = clone(value)
    if (next === undefined || key === 'required' && Array.isArray(next) && next.length === 0) delete updated[key]
    else updated[key] = next
    onChange(updated)
  }
  const wrappedRef = Array.isArray(value.allOf) && value.allOf.length === 1 && value.allOf[0]?.$ref
  const selectedRef = value.$ref || wrappedRef || ''
  const typeValue = Array.isArray(value.type) ? JSON.stringify(value.type) : text(value.type)
  const typeOptions = version.startsWith('3.1') ? [...schemaTypes, 'null', ...schemaTypes.filter(Boolean).map(type => JSON.stringify([type, 'null']))] : schemaTypes
  const hasType = type => value.type === type || Array.isArray(value.type) && value.type.includes(type)
  const refOptions = refs.filter(item => item.ref)
  const properties = Object.entries(value.properties || {})
  const updateProperty = (name, next) => set('properties', { ...value.properties, [name]: next })
  const renameProperty = (name, next) => {
    if (!next || (next !== name && Object.hasOwn(value.properties || {}, next))) return
    const updated = Object.fromEntries(properties.map(([key, entry]) => [key === name ? next : key, entry]))
    const renamed = { ...value, properties: updated, required: (value.required || []).map(key => key === name ? next : key) }
    if (!renamed.required.length) delete renamed.required
    onChange(renamed)
  }
  return <div className="oas-schema">
    <div className="oas-grid">
      <Field label="Schema 참조"><select value={selectedRef} onChange={event => {
        if (event.target.value) {
          const preserved = Object.fromEntries(Object.entries(value).filter(([key]) => key.startsWith('x-') || ['title', 'summary', 'description', 'example'].includes(key)))
          const needsWrapper = version.startsWith('3.0') && (wrappedRef || Object.keys(preserved).some(key => !['summary', 'description'].includes(key)))
          onChange(needsWrapper ? { ...preserved, allOf: [{ $ref: event.target.value }] } : { ...preserved, $ref: event.target.value })
        } else { const next = clone(value); delete next.$ref; if (wrappedRef) delete next.allOf; onChange(next) }
      }}><option value="">직접 정의</option>{refOptions.map(item => <option key={`${item.file}:${item.name}`} value={item.ref}>{item.name}</option>)}{selectedRef && !refOptions.some(item => item.ref === selectedRef) && <option value={selectedRef}>{selectedRef}</option>}</select></Field>
      {!selectedRef && <Field label="타입"><select value={typeValue} onChange={event => set('type', event.target.value.startsWith('[') ? JSON.parse(event.target.value) : event.target.value || undefined)}>{typeOptions.map(type => <option key={type} value={type}>{type.startsWith('[') ? `${JSON.parse(type)[0]} 또는 null` : type || '지정 안 함'}</option>)}{typeValue && !typeOptions.includes(typeValue) && <option value={typeValue}>{typeValue}</option>}</select></Field>}
      <Field label="설명"><input value={text(value.description)} onChange={event => set('description', event.target.value)} /></Field>
      {!selectedRef && <><Field label="format"><input value={text(value.format)} onChange={event => set('format', event.target.value)} placeholder="date-time, uuid…" /></Field>
        <JsonValue label="enum" value={value.enum} onChange={next => set('enum', next)} validate={next => next === undefined || Array.isArray(next)} onValidity={onValidity} id={`${id}.enum`} />
        {version.startsWith('3.0') && <label className="toggle"><input type="checkbox" checked={Boolean(value.nullable)} onChange={event => set('nullable', event.target.checked || undefined)} />nullable (OpenAPI 3.0)</label>}
        {['minimum', 'maximum', 'minLength', 'maxLength', 'minItems', 'maxItems', 'minProperties', 'maxProperties'].map(key => <Field key={key} label={key}><input type="number" value={text(value[key])} onChange={event => set(key, event.target.value === '' ? undefined : Number(event.target.value))} /></Field>)}
        <Field label="pattern"><input value={text(value.pattern)} onChange={event => set('pattern', event.target.value)} /></Field>
        {['exclusiveMinimum', 'exclusiveMaximum'].map(key => version.startsWith('3.0') ? <label key={key} className="toggle"><input type="checkbox" checked={Boolean(value[key])} onChange={event => set(key, event.target.checked || undefined)} />{key}</label> : <Field key={key} label={key}><input type="number" value={text(value[key])} onChange={event => set(key, event.target.value === '' ? undefined : Number(event.target.value))} /></Field>)}
        <JsonValue label="example" value={value.example} onChange={next => set('example', next)} onValidity={onValidity} id={`${id}.example`} /></>}
    </div>
    {!selectedRef && hasType('array') && depth < 2 && <section className="oas-subsection"><h4>items</h4><SchemaFields schema={value.items ?? { type: 'string' }} refs={refs} ownerFile={ownerFile} version={version} onValidity={onValidity} id={`${id}.items`} depth={depth + 1} onChange={next => set('items', next)} /></section>}
    {!selectedRef && hasType('object') && depth < 2 && <section className="oas-subsection"><h4>properties</h4>{properties.map(([name, property]) => <div className="oas-entry" key={name}><div className="oas-entry-heading"><Field label="속성 이름"><input value={name} onChange={event => renameProperty(name, event.target.value)} /></Field><label className="toggle"><input type="checkbox" checked={(value.required || []).includes(name)} onChange={event => set('required', event.target.checked ? [...(value.required || []), name] : (value.required || []).filter(item => item !== name))} />required</label><button className="danger-button" onClick={() => { const next = clone(value); delete next.properties[name]; next.required = (next.required || []).filter(item => item !== name); if (!next.required.length) delete next.required; onChange(next) }}>삭제</button></div><SchemaFields schema={property} refs={refs} ownerFile={ownerFile} version={version} onValidity={onValidity} id={`${id}.properties.${name}`} depth={depth + 1} onChange={next => updateProperty(name, next)} /></div>)}<button className="ghost" onClick={() => { let name = 'newProperty'; let index = 2; while (Object.hasOwn(value.properties || {}, name)) name = `newProperty${index++}`; updateProperty(name, { type: 'string' }) }}>＋ 속성 추가</button></section>}
    <RawObject label="Schema" value={value} onChange={onChange} onValidity={onValidity} id={`${id}.raw`} allowBoolean validate={schemaShape} />
  </div>
}

function MediaFields({ content = {}, onChange, refs, ownerFile, version, onValidity, id = 'media' }) {
  const update = (type, next) => onChange({ ...content, [type]: next })
  return <div className="oas-list">{Object.entries(content || {}).map(([type, media]) => <section className="oas-entry" key={type}><div className="oas-entry-heading"><Field label="Media type"><input value={type} onChange={event => { const next = event.target.value; if (!next || (next !== type && Object.hasOwn(content, next))) return; onChange(Object.fromEntries(Object.entries(content).map(([name, item]) => [name === type ? next : name, item]))) }} /></Field><button className="danger-button" onClick={() => { const next = { ...content }; delete next[type]; onChange(next) }}>삭제</button></div><SchemaFields schema={media.schema ?? {}} refs={refs} ownerFile={ownerFile} version={version} onValidity={onValidity} id={`${id}.${type}.schema`} onChange={schema => update(type, { ...media, schema })} /><JsonValue label="Media example" value={media.example} onValidity={onValidity} id={`${id}.${type}.example`} onChange={example => { const next = { ...media }; if (example === undefined) delete next.example; else next.example = example; update(type, next) }} /><RawObject label="Media" value={media} onValidity={onValidity} id={`${id}.${type}.raw`} validate={mediaShape} onChange={next => update(type, next)} /></section>)}<button className="ghost" onClick={() => { let type = 'application/json'; let index = 2; while (Object.hasOwn(content, type)) type = `application/vnd.example${index++}+json`; update(type, { schema: { type: 'object' } }) }}>＋ Media type 추가</button></div>
}

function HeaderFields({ headers = {}, onChange, refs, ownerFile, version, onValidity, id = 'headers' }) {
  const update = (name, next) => onChange({ ...headers, [name]: next })
  return <div className="oas-list">
    {Object.entries(headers || {}).map(([name, header]) => <section className="oas-entry" key={name}>
      <div className="oas-entry-heading"><Field label="Header 이름"><input value={name} onChange={event => { const next = event.target.value; if (!next || (next !== name && Object.hasOwn(headers, next))) return; onChange(Object.fromEntries(Object.entries(headers).map(([key, value]) => [key === name ? next : key, value]))) }} /></Field><button className="danger-button" onClick={() => { const next = { ...headers }; delete next[name]; onChange(next) }}>삭제</button></div>
      {header.$ref ? <><p className="hint">참조 Header: <code>{header.$ref}</code></p><RawObject label="Header reference" value={header} onChange={next => update(name, next)} onValidity={onValidity} id={`${id}.${name}.raw`} validate={headerShape} /></> : <>
        <Field label="설명"><input value={text(header.description)} onChange={event => update(name, { ...header, description: event.target.value })} /></Field>
        <SchemaFields schema={header.schema ?? { type: 'string' }} refs={refs} ownerFile={ownerFile} version={version} onValidity={onValidity} id={`${id}.${name}.schema`} onChange={schema => update(name, { ...header, schema })} />
      </>}
    </section>)}
    <button className="ghost" onClick={() => { let name = 'X-Header'; let index = 2; while (Object.hasOwn(headers, name)) name = `X-Header-${index++}`; update(name, { description: '', schema: { type: 'string' } }) }}>＋ Header 추가</button>
  </div>
}

export { HeaderFields, JsonValue, MediaFields, RawObject, SchemaFields, operationShape, parameterShape, requestBodyShape, responseShape, securityShape }
