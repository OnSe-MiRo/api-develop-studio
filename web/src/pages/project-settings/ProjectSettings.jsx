import { Field } from '../../components/Field.jsx'
import { OwnershipPanel } from '../../components/OwnershipPanel.jsx'
import { ProjectVariableRows } from '../../components/ProjectVariableRows.jsx'
import { asText, projectFileName, api } from '../../utils/studio.js'
import { useEffect, useState } from 'react'

const emptyProjectForm = () => ({
  name: '', baseUrl: '', docsUrl: '', docsFile: null, docsBundle: null, useProxy: true, sameProxy: false, httpProxy: '', httpsProxy: '', verify: true,
  baseUrls: [], plainVariables: [], secretVariables: [],
})

function BaseUrlRows({ items, onAdd, onUpdate, onRemove }) {
  return <section className="base-url-settings">
    <div className="proxy-settings-heading"><div><strong>추가 Base URL</strong><p className="hint">개발·스테이징·운영처럼 API 케이스별로 선택할 주소를 등록합니다.</p></div><button className="ghost" onClick={onAdd}>＋ Base URL 추가</button></div>
    {items.length ? <div className="base-url-list"><div className="base-url-header"><span>이름</span><span>URL</span><span /></div>{items.map((item, index) => <div className="base-url-row" key={index}><input value={item.name} onChange={event => onUpdate(index, 'name', event.target.value)} placeholder="staging" /><input value={item.url} onChange={event => onUpdate(index, 'url', event.target.value)} placeholder="https://staging-api.example.com" /><button className="icon danger" aria-label={`${index + 1}번째 Base URL 삭제`} onClick={() => onRemove(index)}>×</button></div>)}</div> : <div className="project-variable-empty">추가 Base URL이 없습니다. API 케이스는 기본 주소를 사용합니다.</div>}
  </section>
}

function ProjectSettings({ projects, projectReference, onSaved, onCancel }) {
  const [form, setForm] = useState(emptyProjectForm)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const [storageMeta, setStorageMeta] = useState(null)
  const [docsValidation, setDocsValidation] = useState({ status: 'idle', message: '' })
  const set = (key, value) => setForm(current => ({ ...current, [key]: value }))
  const setSameProxy = checked => setForm(current => {
    const commonProxy = current.httpProxy || current.httpsProxy
    return { ...current, sameProxy: checked, httpProxy: checked ? commonProxy : current.httpProxy, httpsProxy: checked ? commonProxy : current.httpsProxy }
  })
  const setCommonProxy = value => setForm(current => ({ ...current, httpProxy: value, httpsProxy: value }))
  const addVariable = kind => setForm(current => ({ ...current, [kind]: [...current[kind], { name: '', value: '', configured: false }] }))
  const updateVariable = (kind, index, key, value) => setForm(current => ({ ...current, [kind]: current[kind].map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item) }))
  const removeVariable = (kind, index) => setForm(current => ({ ...current, [kind]: current[kind].filter((_, itemIndex) => itemIndex !== index) }))
  const addBaseUrl = () => setForm(current => ({ ...current, baseUrls: [...current.baseUrls, { name: '', url: '' }] }))
  const updateBaseUrl = (index, key, value) => setForm(current => ({ ...current, baseUrls: current.baseUrls.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item) }))
  const removeBaseUrl = index => setForm(current => ({ ...current, baseUrls: current.baseUrls.filter((_, itemIndex) => itemIndex !== index) }))
  const setDocsUrl = value => setForm(current => ({ ...current, docsUrl: value, docsFile: value ? null : current.docsFile, docsBundle: value ? null : current.docsBundle }))
  const checkDocsUrl = async value => {
    const url = asText(value).trim()
    if (!url) {
      setDocsValidation({ status: 'idle', message: '' })
      return { valid: true, message: '' }
    }
    setDocsValidation({ status: 'checking', message: 'OpenAPI 문서를 확인하는 중입니다.' })
    try {
      const data = await api('/api/docs', { method: 'POST', body: JSON.stringify({ url, no_proxy: !form.useProxy }) })
      const message = `${data.operations?.length || 0}개 API를 확인했습니다.`
      setDocsValidation({ status: 'valid', message })
      return { valid: true, message }
    } catch (error) {
      const message = `문서 URL 확인 실패: ${error.message}`
      setDocsValidation({ status: 'error', message })
      return { valid: false, message }
    }
  }
  const selectDocsFile = async event => {
    const input = event.target
    const file = input.files?.[0]
    if (!file) return
    try {
      if (!file.name.toLowerCase().endsWith('.json')) throw new Error('OpenAPI / Swagger 문서는 JSON 파일만 선택할 수 있습니다.')
      if (file.size > 5 * 1024 * 1024) throw new Error('OpenAPI / Swagger JSON 파일은 5MB 이하여야 합니다.')
      const document = JSON.parse(await file.text())
      const data = await api('/api/docs', { method: 'POST', body: JSON.stringify({ document }) })
      setForm(current => ({ ...current, docsUrl: '', docsFile: { name: file.name, document }, docsBundle: null }))
      setNotice(`${file.name}에서 ${data.operations?.length || 0}개 API를 확인했습니다.`)
    } catch (error) { setNotice(error instanceof SyntaxError ? '올바른 JSON 파일이 아닙니다.' : error.message) }
    finally { input.value = '' }
  }
  const isEditing = Boolean(projectReference)
  useEffect(() => {
    if (!projectReference) { setForm(emptyProjectForm()); setAdvancedOpen(false); setStorageMeta(null); setNotice(''); return }
    const load = async () => {
      try {
        const data = await api(`/api/projects/${encodeURIComponent(projectReference)}`)
        const advanced = data.advanced || {}
        const legacyProxy = asText(advanced.proxy)
        const httpProxy = asText(advanced.http_proxy) || legacyProxy
        const httpsProxy = asText(advanced.https_proxy) || legacyProxy
        const variables = data.variables || {}
        const plainVariables = Object.entries(variables.plain || {}).map(([name, value]) => ({ name, value: asText(value), configured: false }))
        const secretVariables = Object.entries(variables.secret || {}).map(([name, definition]) => ({ name, value: '', configured: Boolean(definition?.configured) }))
        const docsFile = data.docs_file?.document ? data.docs_file : null
        const docsBundle = data.docs_bundle?.entrypoint ? data.docs_bundle : null
        const baseUrls = Array.isArray(data.base_urls) ? data.base_urls.map(item => ({ name: asText(item?.name), url: asText(item?.url) })) : []
        setForm({ name: asText(data.name), baseUrl: asText(data.base_url), baseUrls, docsUrl: asText(data.docs_url), docsFile, docsBundle, useProxy: advanced.use_proxy !== false, sameProxy: Boolean(httpProxy && httpProxy === httpsProxy), httpProxy, httpsProxy, verify: advanced.verify ?? true, plainVariables, secretVariables })
        setStorageMeta(data._storage || null)
        setAdvancedOpen(Boolean(httpProxy || httpsProxy || docsFile || docsBundle || plainVariables.length || secretVariables.length) || advanced.verify === false || advanced.use_proxy === false); setNotice('')
      } catch (error) { setNotice(error.message) }
    }
    load()
  }, [projectReference])
  useEffect(() => {
    const url = form.docsUrl.trim()
    if (!url) {
      setDocsValidation({ status: 'idle', message: '' })
      return undefined
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setDocsValidation({ status: 'checking', message: 'OpenAPI 문서를 확인하는 중입니다.' })
      try {
        const data = await api('/api/docs', { method: 'POST', body: JSON.stringify({ url, no_proxy: !form.useProxy }) })
        if (!cancelled) setDocsValidation({ status: 'valid', message: `${data.operations?.length || 0}개 API를 확인했습니다.` })
      } catch (error) {
        if (!cancelled) setDocsValidation({ status: 'error', message: `문서 URL 확인 실패: ${error.message}` })
      }
    }, 500)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [form.docsUrl, form.useProxy])
  const save = async () => {
    try {
      if (!form.name || !form.baseUrl) throw new Error('프로젝트 이름과 Base URL을 입력하세요.')
      const docsCheck = await checkDocsUrl(form.docsUrl)
      if (!docsCheck.valid) throw new Error(docsCheck.message)
      const variableNamePattern = /^[A-Za-z_][A-Za-z0-9_-]*$/
      const baseUrls = [], baseUrlNames = new Set()
      form.baseUrls.forEach((item, index) => {
        const name = asText(item.name).trim(), url = asText(item.url).trim()
        if (!name && !url) return
        if (!name || !url) throw new Error(`추가 Base URL ${index + 1}의 이름과 URL을 모두 입력하세요.`)
        if (baseUrlNames.has(name)) throw new Error(`중복된 Base URL 이름입니다: ${name}`)
        baseUrlNames.add(name); baseUrls.push({ name, url })
      })
      const plain = {}, secret = {}, names = new Set()
      form.plainVariables.forEach((item, index) => {
        const name = asText(item.name).trim()
        if (!name && !item.value) return
        if (!variableNamePattern.test(name)) throw new Error(`일반 변수 ${index + 1}의 변수명 형식이 올바르지 않습니다.`)
        if (names.has(name)) throw new Error(`중복된 프로젝트 변수명입니다: ${name}`)
        names.add(name); plain[name] = asText(item.value)
      })
      form.secretVariables.forEach((item, index) => {
        const name = asText(item.name).trim()
        if (!name && !item.value && !item.configured) return
        if (!variableNamePattern.test(name)) throw new Error(`보안 변수 ${index + 1}의 변수명 형식이 올바르지 않습니다.`)
        if (names.has(name)) throw new Error(`중복된 프로젝트 변수명입니다: ${name}`)
        names.add(name)
        if (item.value) secret[name] = { value: item.value }
        else if (item.configured) secret[name] = { preserve: true }
        else throw new Error(`보안 변수 ${name}의 값을 입력하세요.`)
      })
      const reference = projectReference || projectFileName(form.name, projects)
      const payload = { name: form.name, base_url: form.baseUrl.trim(), base_urls: baseUrls, docs_url: form.docsUrl, advanced: { use_proxy: form.useProxy, http_proxy: form.httpProxy, https_proxy: form.httpsProxy, verify: form.verify }, variables: { plain, secret } }
      if (form.docsFile) payload.docs_file = form.docsFile
      if (form.docsBundle) payload.docs_bundle = form.docsBundle
      await api(`/api/projects/${encodeURIComponent(reference)}`, { method: 'PUT', body: JSON.stringify(projectReference && storageMeta ? { ...payload, _storage: storageMeta } : payload) })
      await onSaved(reference)
    } catch (error) { setNotice(error.message) }
  }
  return <main className="project-page"><section className="card"><div className="section-header"><div><p className="eyebrow">{isEditing ? 'EDIT PROJECT' : 'NEW PROJECT'}</p><h2>프로젝트 설정</h2></div><div className="actions"><button className="ghost" onClick={onCancel}>목록으로</button><button className="primary" onClick={save}>저장</button></div></div><div className="form-grid project-settings-grid"><Field label="프로젝트 이름"><input value={form.name} onChange={event => set('name', event.target.value)} placeholder="New Project" /></Field><Field label="기본 Base URL"><input value={form.baseUrl} onChange={event => set('baseUrl', event.target.value)} placeholder="https://api.example.com" /></Field></div><BaseUrlRows items={form.baseUrls} onAdd={addBaseUrl} onUpdate={updateBaseUrl} onRemove={removeBaseUrl} /><section className="advanced-settings"><button className="advanced-toggle" onClick={() => setAdvancedOpen(current => !current)}><span>설정</span><span>{advancedOpen ? '−' : '+'}</span></button>{advancedOpen && <div className="advanced-content"><section className="proxy-settings"><div className="proxy-settings-heading"><strong>OpenAPI 설정</strong></div><div className="openapi-source-options"><div className="openapi-url-field"><Field label="OpenAPI / Swagger 문서 URL"><input value={form.docsUrl} onChange={event => setDocsUrl(event.target.value)} onBlur={() => checkDocsUrl(form.docsUrl)} placeholder="https://api.example.com/openapi.json" /></Field>{docsValidation.status !== 'idle' && <p className={`openapi-validation ${docsValidation.status}`} role="status" aria-live="polite">{docsValidation.message}</p>}</div><span className="openapi-or">또는</span><div className="field"><span>OpenAPI / Swagger JSON 파일</span><div className="openapi-file-input"><label className="file-picker"><input type="file" accept=".json,application/json" onChange={selectDocsFile} /><span>{form.docsFile?.name || 'JSON 파일 선택'}</span></label>{form.docsFile && <button className="ghost" onClick={() => setForm(current => ({ ...current, docsFile: null }))}>제거</button>}</div></div></div><p className="hint">문서 URL과 JSON 파일 중 하나를 등록할 수 있습니다. URL을 입력하면 자동으로 문서 형식과 API 목록을 확인하고, 실패 원인을 표시합니다.</p></section><section className="project-variable-settings"><div className="proxy-settings-heading"><div><strong>프로젝트 공통 변수</strong><p className="hint">API 케이스에서 <code>{'{{project.변수명}}'}</code>으로 불러옵니다.</p></div></div><ProjectVariableRows items={form.plainVariables} onAdd={() => addVariable('plainVariables')} onUpdate={(index, key, value) => updateVariable('plainVariables', index, key, value)} onRemove={index => removeVariable('plainVariables', index)} /><ProjectVariableRows secret items={form.secretVariables} onAdd={() => addVariable('secretVariables')} onUpdate={(index, key, value) => updateVariable('secretVariables', index, key, value)} onRemove={index => removeVariable('secretVariables', index)} /></section><section className="proxy-settings"><div className="proxy-settings-heading"><strong>Proxy 설정</strong></div><label className="toggle"><input type="checkbox" checked={!form.useProxy} onChange={event => set('useProxy', !event.target.checked)} /><span>프록시 사용 안 함 (No Proxy)</span></label>{form.sameProxy ? <Field label="Proxy URL (HTTP/HTTPS)"><input disabled={!form.useProxy} value={form.httpProxy} onChange={event => setCommonProxy(event.target.value)} placeholder="http://proxy.example.com:8080" /></Field> : <div className="form-grid project-settings-grid"><Field label="HTTP Proxy URL"><input disabled={!form.useProxy} value={form.httpProxy} onChange={event => set('httpProxy', event.target.value)} placeholder="http://proxy.example.com:8080" /></Field><Field label="HTTPS Proxy URL"><input disabled={!form.useProxy} value={form.httpsProxy} onChange={event => set('httpsProxy', event.target.value)} placeholder="http://proxy.example.com:8080" /></Field></div>}<label className={`toggle ${!form.useProxy ? 'disabled' : ''}`}><input disabled={!form.useProxy} type="checkbox" checked={form.sameProxy} onChange={event => setSameProxy(event.target.checked)} /><span>HTTP/HTTPS 공통 주소 사용</span></label><p className="hint">프록시 사용 안 함을 선택하면 저장된 주소와 환경 프록시를 모두 우회합니다. 해제하면 입력한 프록시 주소를 사용하며, 주소를 비우면 직접 연결합니다.</p></section><label className="toggle"><input type="checkbox" checked={form.verify} onChange={event => set('verify', event.target.checked)} /><span>TLS 인증서 검증 (verify)</span></label><p className="hint">verify를 끄면 자체 서명 인증서 등의 TLS 검증을 생략합니다.</p></div>}</section><p className="hint">{isEditing ? <>프로젝트 파일명 <code>{projectReference}</code>은 유지됩니다. 변경한 Base URL, API 문서와 공통 변수는 연결된 API 케이스와 파이프라인 실행에 즉시 적용됩니다.</> : <>프로젝트 JSON 파일은 프로젝트 이름을 기준으로 자동 생성됩니다. 케이스의 URL·Params·Authorization·Headers·Body에서 <code>{'{{project.변수명}}'}</code>을 사용할 수 있습니다.</>}</p></section>{projectReference && <OwnershipPanel projectReference={projectReference} />}{notice && <p className="notice">{notice}</p>}</main>
}

export { ProjectSettings }
