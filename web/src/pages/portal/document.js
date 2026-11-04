const methods = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace']
export function resolve(document, input) {
  let value = input
  const seen = new Set()
  while (value && typeof value === 'object' && typeof value.$ref === 'string') {
    const ref = value.$ref
    if (!ref.startsWith('#/') || seen.has(ref)) return null
    seen.add(ref)
    try {
      value = document
      for (const part of decodeURIComponent(ref.slice(2)).split('/')) {
        const key = part.replaceAll('~1', '/').replaceAll('~0', '~')
        if (!value || !Object.hasOwn(value, key)) return null
        value = value[key]
      }
    } catch { return null }
  }
  return value
}

export function operations(document) {
  const result = []
  for (const [path, value] of Object.entries(document.paths || {})) {
    const pathItem = resolve(document, value)
    if (!pathItem) continue
    for (const method of methods) {
      const operation = resolve(document, pathItem[method])
      if (!operation) continue
      const parameters = new Map()
      for (const raw of [...(pathItem.parameters || []), ...(operation.parameters || [])]) {
        const parameter = resolve(document, raw)
        if (parameter) parameters.set(`${parameter.in}:${parameter.name}`, parameter)
      }
      result.push({ ...operation, key: `${method}:${path}`, path, method: method.toUpperCase(),
        parameters: [...parameters.values()], servers: operation.servers || pathItem.servers || document.servers || [],
        security: operation.security === undefined ? document.security || [] : operation.security })
    }
  }
  return result
}

export function searchOperations(items, search) {
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean)
  return items.filter(item => {
    const text = [item.path, item.method, item.operationId, item.summary, item.description, ...(item.tags || [])].join(' ').toLowerCase()
    return words.every(word => text.includes(word))
  })
}

export function schemaExample(document, raw, budget = { remaining: 200 }, depth = 0, refs = new Set()) {
  if (depth > 4 || --budget.remaining < 0) return null
  if (raw?.$ref) {
    if (refs.has(raw.$ref)) return null
    refs = new Set(refs); refs.add(raw.$ref)
  }
  const schema = resolve(document, raw)
  if (!schema || typeof schema !== 'object') return null
  for (const key of ['example', 'default']) if (Object.hasOwn(schema, key)) return schema[key]
  if (schema.enum?.length) return schema.enum[0]
  if (schema.oneOf?.length || schema.anyOf?.length) return schemaExample(document, (schema.oneOf || schema.anyOf)[0], budget, depth + 1, refs)
  if (schema.type === 'object' || schema.properties) return Object.fromEntries(Object.entries(schema.properties || {}).slice(0, 20).map(([key, value]) => [key, schemaExample(document, value, budget, depth + 1, refs)]))
  if (schema.type === 'array') return [schemaExample(document, schema.items, budget, depth + 1, refs)]
  if (schema.type === 'integer' || schema.type === 'number') return 0
  if (schema.type === 'boolean') return false
  if (schema.type === 'null') return null
  return 'example'
}

export function examples(document, media) {
  if (!media) return []
  if (Object.hasOwn(media, 'example')) return [{ name: '명세 예시', value: media.example }]
  const explicit = Object.entries(media.examples || {}).flatMap(([name, raw]) => {
    const example = resolve(document, raw)
    return example && Object.hasOwn(example, 'value') ? [{ name, value: example.value }] : []
  })
  if (explicit.length) return explicit
  return media.schema ? [{ name: 'schema에서 만든 설명용 예시 (깊이·항목 제한)', value: schemaExample(document, media.schema) }] : []
}

export function servers(operation, environments) {
  return [...(operation?.servers || []).map(server => ({ name: server.description || 'OpenAPI server', url: String(server.url || '').replace(/\{([^}]+)\}/g, (match, name) => server.variables?.[name]?.default ?? match) })), ...(environments || [])]
}
