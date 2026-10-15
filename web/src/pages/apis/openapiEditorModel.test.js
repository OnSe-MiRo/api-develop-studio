import { expect, it } from 'vitest'
import { editorEdit, pointerValue } from './openapiEditorModel.js'

it('reads only owned raw JSON Pointer targets, including escaped paths and root booleans', () => {
  expect(pointerValue({ paths: { '/items': { get: { summary: 'raw' } } } }, '#/paths/~1items/get')).toEqual({ summary: 'raw' })
  expect(pointerValue(false, '#')).toBe(false)
  expect(() => pointerValue({}, '#/constructor')).toThrow('원본 파일에서 편집 위치')
})

it('removes an external component declaration without deleting its shared owner file', () => {
  const owner = { file: 'openapi.yaml', pointer: '#/components/schemas/Pet', exists: true }
  expect(editorEdit(owner, null, true)).toEqual({ file: 'openapi.yaml', op: 'remove', path: '#/components/schemas/Pet' })
})
