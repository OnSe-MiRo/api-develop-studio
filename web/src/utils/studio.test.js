import { describe, expect, it } from 'vitest'
import { appendParams, parseHeaders, parseJson, splitRequestUrl } from './studio.js'

describe('form transformations', () => {
  it('splits and rebuilds repeated query parameters', () => {
    const result = splitRequestUrl('https://api.example.test/users?role=admin&role=editor')
    expect(result).toEqual({
      baseUrl: 'https://api.example.test/users',
      params: [{ key: 'role', value: 'admin' }, { key: 'role', value: 'editor' }],
    })
    expect(appendParams(result.baseUrl, result.params)).toBe('https://api.example.test/users?role=admin&role=editor')
  })

  it('parses headers and reports the failing line', () => {
    expect(parseHeaders('Accept: application/json\nX-Trace: one:two')).toEqual({
      Accept: 'application/json', 'X-Trace': 'one:two',
    })
    expect(() => parseHeaders('Accept application/json')).toThrow('Headers 1번째 줄')
  })

  it('distinguishes optional empty JSON from malformed JSON', () => {
    expect(parseJson('', 'Body')).toBeUndefined()
    expect(parseJson('{"ok":true}', 'Body')).toEqual({ ok: true })
    expect(() => parseJson('{', 'Body')).toThrow('Body JSON 형식')
  })
})
