import { expect, it } from 'vitest'
import { examples, operations, resolve, schemaExample, searchOperations, servers } from './document.js'
const document = {
  openapi: '3.0.3', security: [{ bearer: [] }],
  servers: [{ url: 'https://{env}.example.test', variables: { env: { default: 'dev' } } }],
  paths: {
    '/items/{id}': {
      parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
      get: { operationId: 'getItem', summary: '상품 조회', tags: ['items'], responses: { 200: { description: 'ok' } } },
      delete: { security: [], deprecated: true, responses: { 204: { description: 'deleted' } } },
    },
  },
  components: {
    schemas: { Node: { type: 'object', properties: { child: { $ref: '#/components/schemas/Node' } } } },
    examples: { Item: { value: { id: 7 } } },
  },
}

it('preserves inherited and overridden parameters, security and servers', () => {
  const items = operations(document)
  expect(items[0].parameters[0].name).toBe('id')
  expect(items[0].security).toEqual([{ bearer: [] }])
  expect(items[1].security).toEqual([])
  expect(servers(items[0], [{ name: 'prod', url: 'https://prod.example.test' }])[0].url).toBe('https://dev.example.test')
})
it('searches method, path, operationId, Korean summary and tags without regex execution', () => {
  const items = operations(document)
  expect(searchOperations(items, 'GET 상품')).toHaveLength(1)
  expect(searchOperations(items, 'items')).toHaveLength(2)
  expect(searchOperations(items, 'getItem')[0].method).toBe('GET')
  expect(searchOperations(items, '.*')).toHaveLength(0)
})
it('resolves local examples, respects explicit null and bounds recursive samples', () => {
  expect(examples(document, { example: null })[0].value).toBeNull()
  expect(examples(document, { examples: { named: { $ref: '#/components/examples/Item' } } })[0].value).toEqual({ id: 7 })
  expect(JSON.stringify(schemaExample(document, { $ref: '#/components/schemas/Node' })).length).toBeLessThan(100)
})
it('never follows external refs or prototype properties', () => {
  expect(resolve(document, { $ref: 'https://example.test/private' })).toBeNull()
  expect(resolve(document, { $ref: '#/__proto__' })).toBeNull()
  expect(examples(document, { examples: { outside: { externalValue: 'https://example.test/secret' } } })).toEqual([])
})
