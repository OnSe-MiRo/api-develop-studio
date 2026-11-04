export const clone = value => structuredClone(value)
export const escapePointer = value => String(value).replaceAll('~', '~0').replaceAll('/', '~1')
export const pointerValue = (document, pointer) => {
  if (pointer === '#') return document
  if (!pointer?.startsWith('#/')) throw new Error('올바르지 않은 JSON Pointer입니다.')
  return pointer.slice(2).split('/').reduce((value, key) => {
    const decoded = key.replaceAll('~1', '/').replaceAll('~0', '~')
    if (value === null || typeof value !== 'object' || !Object.hasOwn(value, decoded)) throw new Error('원본 파일에서 편집 위치를 찾을 수 없습니다.')
    return value[decoded]
  }, document)
}
export const operationOwner = (catalog, operation) => (catalog?.operations || []).find(item =>
  item.method.toUpperCase() === operation.method.toUpperCase() && item.path === operation.path)
export const namedOwner = (catalog, kind, name) => (catalog?.[kind] || []).find(item => item.name === name)
export const editorEdit = (owner, value, remove = false) => ({
  file: owner.file,
  op: remove ? 'remove' : owner.exists ? 'replace' : 'add',
  path: owner.pointer || owner.path,
  ...(remove ? {} : { value }),
})
export const parseJsonValue = (text, label) => {
  if (!text.trim()) return undefined
  try { return JSON.parse(text) } catch { throw new Error(`${label}: 올바른 JSON을 입력하세요.`) }
}
