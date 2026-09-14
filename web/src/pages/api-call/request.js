export function quickRequest({ method, url, params, headers, body, bodyMode, authType, authValues, authProfile }) {
  const request = { method, url: url.trim(), headers: {} }
  const query = new URLSearchParams(params.filter(item => item.key.trim()).map(item => [item.key.trim(), item.value])).toString()
  if (query) {
    const [base, fragment] = request.url.split('#')
    request.url = `${base}${base.includes('?') ? '&' : '?'}${query}${fragment ? `#${fragment}` : ''}`
  }
  for (const line of headers.split('\n').filter(line => line.trim() && !line.trim().startsWith('#'))) {
    const colon = line.indexOf(':')
    if (colon < 1) throw new Error('헤더는 이름: 값 형식으로 입력하세요.')
    request.headers[line.slice(0, colon).trim()] = line.slice(colon + 1).trim()
  }
  if (authProfile) request.auth_profile = authProfile
  else request.auth = { type: authType, ...authValues }
  if (!['GET', 'HEAD'].includes(method) && body !== '') {
    if (bodyMode === 'json') request.body = JSON.parse(body)
    else if (bodyMode === 'form-data') request.form_data = JSON.parse(body)
    else request.text = body
  }
  return request
}

const sensitive = /authorization|cookie|token|secret|password|api[-_]?key/i
const quote = value => `'${String(value).replaceAll("'", "'\\''")}'`
export function requestCurl(request) {
  const url = request.url.replace(/([?&])([^=&]+)=([^&#]*)/g, (all, separator, key) => sensitive.test(decodeURIComponent(key)) ? `${separator}${key}=***` : all)
  const parts = ['curl', '-X', quote(request.method), quote(url)]
  for (const [key, value] of Object.entries(request.headers)) parts.push('-H', quote(`${key}: ${sensitive.test(key) ? '***' : value}`))
  const auth = request.auth || {}
  if (request.auth_profile) parts.push('-H', quote('Authorization: ***'))
  else if (auth.type === 'API Key') {
    if (auth.addTo === 'Query Params') parts.push('--url-query', quote(`${auth.key}=***`))
    else parts.push('-H', quote(`${auth.key}: ***`))
  } else if (auth.type && auth.type !== 'No Auth') parts.push('-H', quote('Authorization: ***'))
  const redact = value => {
    if (Array.isArray(value)) return value.map(redact)
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, sensitive.test(key) ? '***' : redact(item)]))
    return value
  }
  if ('body' in request) parts.push('-H', quote('Content-Type: application/json'), '--data', quote(JSON.stringify(redact(request.body))))
  if ('text' in request) parts.push('-H', quote('Content-Type: text/plain'), '--data', quote('[텍스트 본문 생략]'))
  if (Array.isArray(request.form_data)) for (const item of request.form_data) parts.push('-F', quote(`${item.key}=${item.file ? '@' + item.file : sensitive.test(item.key) ? '***' : item.value}`))
  let command = parts.join(' ')
  for (const [key, value] of Object.entries(auth)) if ((sensitive.test(key) || key === 'value') && value) command = command.replaceAll(String(value), '***')
  return command
}
