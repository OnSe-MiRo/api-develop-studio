import { describe, it, expect } from 'vitest'
import { quickRequest, requestCurl } from './request.js'
const input = { method: 'POST', url: 'https://example.test/path?x=1#part', params: [{ key: 'x', value: '2' }, { key: 'x', value: '한글' }], headers: 'X-Test: value', body: '{"a":1}', bodyMode: 'json', authType: 'No Auth', authValues: {} }
describe('quick request conversion', () => {
  it('preserves query ordering, repeats, fragments and JSON for case storage', () => {
    const request = quickRequest(input)
    expect(request.url).toBe('https://example.test/path?x=1&x=2&x=%ED%95%9C%EA%B8%80#part')
    expect(request.body).toEqual({ a: 1 })
    expect(request.headers).toEqual({ 'X-Test': 'value' })
  })
  it('keeps text whitespace and multipart structure', () => {
    expect(quickRequest({ ...input, bodyMode: 'text', body: '  hello\n' }).text).toBe('  hello\n')
    expect(quickRequest({ ...input, bodyMode: 'form-data', body: '[{"key":"x","value":"y"}]' }).form_data).toEqual([{ key: 'x', value: 'y' }])
  })
  it('stores profile references without inline credentials', () => {
    const request = quickRequest({ ...input, authProfile: 'login', authValues: { token: 'private' } })
    expect(request.auth_profile).toBe('login')
    expect(request.auth).toBeUndefined()
    expect(JSON.stringify(request)).not.toContain('private')
  })
  it('masks credentials in copied curl and quotes shell characters', () => {
    const curl = requestCurl({ ...quickRequest(input), url: 'https://example.test/?token=private', headers: { Authorization: 'Bearer private' }, body: { token: 'private' } })
    expect(curl).not.toContain('private')
    expect(curl).toContain('Authorization: ***')
  })
})
