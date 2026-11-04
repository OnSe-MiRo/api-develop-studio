import { Field } from '../../components/Field.jsx'

export function caseContractPayload(form) {
  if (!form.contractEnabled) return {}
  const config = { enabled: true }
  if (form.contractVariables?.trim()) {
    let values
    try { values = JSON.parse(form.contractVariables) } catch { throw new Error('계약 server 변수는 JSON 객체로 입력하세요.') }
    if (!values || Array.isArray(values) || typeof values !== 'object' || Object.keys(values).length > 32 || Object.entries(values).some(([key, value]) => !key || key.length > 128 || typeof value !== 'string' || value.length > 512 || /[\u0000-\u001f]/.test(key + value))) {
      throw new Error('계약 server 변수의 이름과 문자열 값을 확인하세요.')
    }
    config.server_variables = values
  }
  if (form.contractDocumentUrl?.trim()) {
    const value = form.contractDocumentUrl.trim()
    let parsed
    try { parsed = new URL(value) } catch { throw new Error('계약 문서 기준 URL을 확인하세요.') }
    if (!/^https?:\/\//i.test(value) || value.length > 2048 || /[\s\\]/.test(value) || parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error('계약 문서 기준 URL에는 HTTP(S) 주소만 입력하세요. 사용자정보·query·fragment는 사용할 수 없습니다.')
    config.document_url = value
  }
  return { contract_validation: config }
}

export function CaseContractSettings({ form, set }) {
  return <section className="card" aria-label="케이스 OpenAPI 계약 검증">
    <h2>OpenAPI 응답 계약</h2>
    <label className="toggle"><input type="checkbox" checked={Boolean(form.contractEnabled)} onChange={event => set('contractEnabled', event.target.checked)} />저장된 프로젝트 명세로 응답 검증</label>
    <p className="hint">실행 시 프로젝트에 저장된 명세를 사용합니다. 기존 기대 응답 검사와 함께 적용되며, 이 케이스를 실행하는 파이프라인에도 적용됩니다. 명세나 operation이 유효하지 않으면 호출 전에 중단합니다.</p>
    {form.contractEnabled && <><Field label="계약 server 변수 (JSON)"><textarea rows={3} value={form.contractVariables || ''} onChange={event => set('contractVariables', event.target.value)} placeholder={'{"version":"v2"}'} /></Field>
    <Field label="계약 문서 기준 URL"><input value={form.contractDocumentUrl || ''} onChange={event => set('contractDocumentUrl', event.target.value)} placeholder="https://example.test/spec/openapi.json" maxLength={2048} /></Field>
    <p className="hint">선택 설정입니다. 이 값은 케이스에 저장되므로 인증정보를 입력하지 마세요. 문서 URL을 다운로드하거나 실제 요청 URL을 변경하지 않습니다.</p></>}
  </section>
}
