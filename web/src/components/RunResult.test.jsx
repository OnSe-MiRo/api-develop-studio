import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { RunResult } from './RunResult.jsx'
const call = { mode: 'call_only', request: { method: 'POST', url: 'https://example.test/items', headers: { Authorization: '***REDACTED***' }, body: { name: 'Ada' } }, response: { status: 503, headers: { 'Retry-After': '5' }, body: 'unavailable' }, elapsedMs: 12.5 }
it('shows actual request, error HTTP response and downloads the completed snapshot', () => {
  let blob
  vi.stubGlobal('URL', class extends URL { static createObjectURL(value) { blob = value; return 'blob:snapshot' } static revokeObjectURL() {} })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const result = { runId: 'run-1', status: 'passed', output: `  call_details=${JSON.stringify(call)}\nDone` }
  render(<RunResult result={result} />)
  expect(screen.getByText(/HTTP 503/)).toBeInTheDocument()
  expect(screen.getByText('12.50 ms')).toBeInTheDocument()
  expect(screen.getByText('응답 검증 안 함', { exact: false })).toBeInTheDocument()
  expect(screen.getByText('unavailable')).toBeInTheDocument()
  fireEvent.click(screen.getByText('요청 정보 · 헤더 / 본문'))
  expect(screen.getByText(/REDACTED/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '실행 결과 JSON 다운로드' }))
  expect(blob.type).toBe('application/json;charset=utf-8')
  expect(click.mock.instances[0].download).toBe('api-result-run-1.json')
  return new Promise(resolve => { const reader = new FileReader(); reader.onload = () => { expect(JSON.parse(reader.result)).toMatchObject({ runId: 'run-1', calls: [call], incomplete: false }); vi.unstubAllGlobals(); resolve() }; reader.readAsText(blob) })
})
it('supports old responses and indicates truncated call details', () => {
  render(<RunResult result={{ status: 'failed', output: 'actual_response={"status":404,"body":"missing"}\ncall_details={"request":' }} />)
  expect(screen.getByText(/missing/)).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('일부가 잘렸거나')
  expect(screen.getByText('실행 실패').closest('section')).toHaveClass('failure')
})
it('does not offer export before completion and shows a transport error without response', () => {
  const { rerender } = render(<RunResult result={{ runId: 'running', status: 'running' }} />)
  expect(screen.queryByRole('button', { name: /다운로드/ })).not.toBeInTheDocument()
  rerender(<RunResult result={{ status: 'error', output: `call_details=${JSON.stringify({ ...call, response: null, error: 'timed out' })}` }} />)
  expect(screen.getByText(/응답 없음/)).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('timed out')
})
