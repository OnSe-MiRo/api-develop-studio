const emptyCase = {
  tag: 'sample', apiName: 'api_name', fileName: 'new_case', timeout: '', baseUrlName: '', method: 'GET', url: '',
  params: [{ key: '', value: '' }], authType: 'No Auth', authValues: {}, headers: '', body: '', bodyMode: 'json', formData: [],
  expectedStatus: '200', maxResponseTimeMs: '', strict: true, expectedBody: '', validateExact: true, validateConditions: false, assertions: [], secretVariables: [],
}

const asText = value => typeof value === 'string' ? value : ''

const docValue = value => value === undefined || value === null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)

const emptyFormDataRow = () => ({ key: '', kind: 'text', value: '', file: null, storedFile: '', filename: '', contentType: '' })

const jsonType = value => value === null ? 'null' : Array.isArray(value) ? 'array' : Number.isInteger(value) ? 'integer' : typeof value === 'number' ? 'number' : typeof value === 'string' ? 'string' : typeof value === 'boolean' ? 'boolean' : 'object'

const typeLabel = type => ({ number: '숫자', integer: '정수', string: '문자열', boolean: 'boolean', object: '객체', array: '배열', null: 'null' }[type] || type)

const defaultAssertionOperator = type => type === 'string' || type === 'array' ? 'length_between' : ['boolean', 'object', 'null'].includes(type) ? 'type' : 'between'

const emptyAssertionRow = variable => {
  const operator = defaultAssertionOperator(variable?.type)
  return { path: variable?.path || 'body.', operator, value: operator === 'type' ? variable?.type || 'number' : '', format: 'none', pattern: '', min: '', max: '', includeMin: true, includeMax: true, confirmed: false }
}

const assertionOperators = [
  ['between', '범위 내'], ['gte', '이상'], ['gt', '초과'], ['lte', '이하'], ['lt', '미만'],
  ['exists', '필드 존재'], ['not_exists', '필드 미존재'], ['type', '데이터 타입'], ['length_between', '길이 범위'],
]

const assertionTypes = [['number', '숫자'], ['integer', '정수'], ['string', '문자열'], ['boolean', 'boolean'], ['object', '객체'], ['array', '배열'], ['null', 'null']]

const stringFormats = [
  ['none', '검증 안 함'],
  ['base64url', 'Base64 URL (base64url, deprecated)'], ['binary', '바이너리 (binary, deprecated)'], ['byte', 'Base64 (byte, deprecated)'], ['char', '단일 문자 (char)'],
  ['commonmark', 'CommonMark (commonmark)'], ['date-time-local', '로컬 날짜·시간 (date-time-local)'], ['date-time', '날짜·시간 (date-time)'], ['date', '날짜 (date)'],
  ['decimal', '고정 소수 (decimal)'], ['decimal128', 'Decimal128 (decimal128)'], ['duration', '기간 (duration)'], ['email', '이메일 (email)'],
  ['hostname', '호스트명 (hostname)'], ['html', 'HTML (html)'], ['http-date', 'HTTP 날짜 (http-date)'], ['idn-email', '국제화 이메일 (idn-email)'],
  ['idn-hostname', '국제화 호스트명 (idn-hostname)'], ['int64', '64비트 정수 (int64)'], ['ipv4-cidr', 'IPv4 CIDR (ipv4-cidr)'], ['ipv4', 'IPv4 (ipv4)'],
  ['ipv6-cidr', 'IPv6 CIDR (ipv6-cidr)'], ['ipv6', 'IPv6 (ipv6)'], ['iri-reference', 'IRI 참조 (iri-reference)'], ['iri', 'IRI (iri)'],
  ['json-pointer', 'JSON 포인터 (json-pointer)'], ['language', '언어 태그 (language)'], ['media-range', '미디어 범위 (media-range)'], ['password', '비밀번호 (password)'],
  ['regex', '정규식 문자열 (regex)'], ['relative-json-pointer', '상대 JSON 포인터 (relative-json-pointer)'], ['sf-binary', 'Structured Field 이진값 (sf-binary)'],
  ['sf-boolean', 'Structured Field 불리언 (sf-boolean)'], ['sf-string', 'Structured Field 문자열 (sf-string)'], ['sf-token', 'Structured Field 토큰 (sf-token)'],
  ['time-local', '로컬 시간 (time-local)'], ['time', '시간 (time)'], ['uint64', '부호 없는 64비트 정수 (uint64)'], ['unixtime', 'Unix 시간 (unixtime)'],
  ['uri-reference', 'URI 참조 (uri-reference)'], ['uri-template', 'URI 템플릿 (uri-template)'], ['uri', 'URI (uri)'], ['uuid', 'UUID (uuid)'],
  ['custom', '기타 (정규식)'],
]

const stringFormatLabel = format => stringFormats.find(([value]) => value === format)?.[1] || format

const commonErrorOptions = [[400, 'Bad Request'], [401, 'Unauthorized'], [403, 'Forbidden'], [404, 'Not Found'], [409, 'Conflict'], [500, 'Internal Server Error']]

const assertionFormRow = assertion => {
  const legacyFormat = assertion?.operator === 'format'
  return {
    path: asText(assertion?.path), operator: legacyFormat ? 'type' : asText(assertion?.operator) || 'between',
    value: legacyFormat ? 'string' : assertion?.value === undefined ? '' : String(assertion.value),
    format: legacyFormat ? asText(assertion?.value) || 'none' : asText(assertion?.format) || 'none',
    pattern: asText(assertion?.pattern),
    min: assertion?.min === undefined ? '' : String(assertion.min), max: assertion?.max === undefined ? '' : String(assertion.max),
    includeMin: assertion?.include_min ?? true, includeMax: assertion?.include_max ?? true, confirmed: true,
  }
}

const assertionCanConfirm = assertion => {
  if (!asText(assertion.path).trim()) return false
  if (assertion.operator === 'between' || assertion.operator === 'length_between') {
    if (asText(assertion.min).trim() === '' || asText(assertion.max).trim() === '') return false
    const min = Number(assertion.min), max = Number(assertion.max)
    if (!Number.isFinite(min) || !Number.isFinite(max) || min > max) return false
    return assertion.operator !== 'length_between' || (Number.isInteger(min) && Number.isInteger(max) && min >= 0)
  }
  if (['gt', 'gte', 'lt', 'lte'].includes(assertion.operator)) return asText(assertion.value).trim() !== '' && Number.isFinite(Number(assertion.value))
  if (assertion.operator === 'type') {
    if (!assertionTypes.some(([value]) => value === assertion.value)) return false
    if (assertion.value !== 'string') return true
    const format = assertion.format || 'none'
    return stringFormats.some(([value]) => value === format) && (format !== 'custom' || asText(assertion.pattern).trim() !== '')
  }
  return true
}

const assertionSummary = assertion => {
  const path = asText(assertion.path).trim() || '응답 경로 미지정'
  if (assertion.operator === 'between') return `${path} · ${assertion.min} ${assertion.includeMin ? '이상' : '초과'} · ${assertion.max} ${assertion.includeMax ? '이하' : '미만'}`
  if (assertion.operator === 'length_between') return `${path} · 길이 ${assertion.min}~${assertion.max}`
  if (assertion.operator === 'type') {
    if (assertion.value !== 'string') return `${path} · 타입 ${typeLabel(assertion.value)}`
    const format = assertion.format || 'none'
    return format === 'custom' ? `${path} · 타입 문자열 · 정규식 ${assertion.pattern}` : `${path} · 타입 문자열 · 형식 ${stringFormatLabel(format)}`
  }
  if (assertion.operator === 'exists') return `${path} · 필드 존재`
  if (assertion.operator === 'not_exists') return `${path} · 필드 미존재`
  const operatorLabel = Object.fromEntries(assertionOperators)[assertion.operator] || assertion.operator
  return `${path} · ${assertion.value} ${operatorLabel}`
}

const newCaseForm = () => ({ ...emptyCase, params: [{ key: '', value: '' }], formData: [], assertions: [] })

function responseVariablesFromJson(rawValue) {
  let body
  try { body = JSON.parse(asText(rawValue)) } catch { return [] }
  const variables = []
  const visit = (value, path) => {
    const type = jsonType(value)
    const example = type === 'object' ? `{${Object.keys(value).length}개 키}` : type === 'array' ? `[${value.length}개 항목]` : JSON.stringify(value)
    variables.push({ path, type, example })
    if (type === 'object') Object.entries(value).filter(([key]) => /^[A-Za-z_][\w-]*$/.test(key)).forEach(([key, item]) => visit(item, `${path}.${key}`))
    if (type === 'array') value.forEach((item, index) => visit(item, `${path}.${index}`))
  }
  if (jsonType(body) === 'object') {
    Object.entries(body).filter(([key]) => /^[A-Za-z_][\w-]*$/.test(key)).forEach(([key, item]) => visit(item, `body.${key}`))
  } else {
    visit(body, 'body')
  }
  return variables
}

function jsonFileName(value) {
  const fileName = asText(value).trim()
  return fileName.endsWith('.json') ? fileName : `${fileName}.json`
}

function caseName(value) {
  return asText(value).replace(/\.json$/i, '')
}

const groupDocOperationsByTag = operations => {
  const groups = new Map()
  operations.forEach(operation => {
    const tag = asText(operation.tag).trim() || '태그 없음'
    groups.set(tag, [...(groups.get(tag) || []), operation])
  })
  return [...groups]
}

const operationIdFrom = (method, path) => `${method.toLowerCase()}${asText(path).split(/[^A-Za-z0-9]+/).filter(Boolean).map(part => part[0].toUpperCase() + part.slice(1)).join('') || 'Resource'}`

function projectFileName(name, existingProjects) {
  const baseName = asText(name).trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'project'
  let suffix = 1
  let reference = `${baseName}.json`
  while (existingProjects.includes(reference)) {
    suffix += 1
    reference = `${baseName}-${suffix}.json`
  }
  return reference
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || '요청 처리에 실패했습니다.')
  return data
}

async function uploadAttachment(reference, file) {
  const response = await fetch(`/api/uploads/${encodeURIComponent(reference)}`, {
    method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || '파일 업로드에 실패했습니다.')
  return data.path
}

function parseJson(value, name, required = false) {
  const text = asText(value)
  if (!text.trim()) {
    if (required) throw new Error(`${name}을(를) 입력하세요.`)
    return undefined
  }
  try { return JSON.parse(text) } catch { throw new Error(`${name} JSON 형식이 올바르지 않습니다.`) }
}

function parseHeaders(value) {
  return asText(value).split('\n').reduce((headers, line, index) => {
    if (!line.trim()) return headers
    const separator = line.indexOf(':')
    if (separator < 1) throw new Error(`Headers ${index + 1}번째 줄은 이름: 값 형식이어야 합니다.`)
    headers[line.slice(0, separator).trim()] = line.slice(separator + 1).trim()
    return headers
  }, {})
}

function caseSignature(reference, payload) {
  const expected = payload?.expected || {}
  const expectedBodyRaw = typeof payload?._expectedBodyRaw === 'string'
    ? payload._expectedBodyRaw
    : expected.body === undefined ? '' : JSON.stringify(expected.body, null, 2)
  return JSON.stringify({ reference, project: payload?.project, baseUrlName: payload?.base_url_name, timeout: payload?.timeout, request: payload?.request, expected, expectedBodyRaw })
}

function splitRequestUrl(rawUrl) {
  const value = asText(rawUrl)
  try {
    const url = new URL(value)
    return {
      baseUrl: `${url.origin}${url.pathname}${url.hash}`,
      params: [...url.searchParams.entries()].map(([key, value]) => ({ key, value })),
    }
  } catch {
    // Imported cases may contain a relative URL or a template expression. Keep it editable instead of crashing.
    const queryIndex = value.indexOf('?')
    if (queryIndex < 0) return { baseUrl: value, params: [] }
    return {
      baseUrl: value.slice(0, queryIndex),
      params: [...new URLSearchParams(value.slice(queryIndex + 1)).entries()].map(([key, value]) => ({ key, value })),
    }
  }
}

function appendParams(rawUrl, params) {
  const entries = params.filter(item => item.key)
  if (!entries.length) return rawUrl
  const query = new URLSearchParams(entries.map(item => [item.key, item.value])).toString()
  return `${rawUrl}${rawUrl.includes('?') ? '&' : '?'}${query}`
}

export { emptyCase, asText, docValue, emptyFormDataRow, jsonType, typeLabel, defaultAssertionOperator, emptyAssertionRow, assertionOperators, assertionTypes, stringFormats, stringFormatLabel, commonErrorOptions, assertionFormRow, assertionCanConfirm, assertionSummary, newCaseForm, responseVariablesFromJson, jsonFileName, caseName, groupDocOperationsByTag, operationIdFrom, projectFileName, api, uploadAttachment, parseJson, parseHeaders, caseSignature, splitRequestUrl, appendParams }
