import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SavedCaseResults } from './SavedCaseResults.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', async original => ({ ...await original(), api: vi.fn() }))
beforeEach(() => vi.resetAllMocks())
it('explicitly saves the completed run and reopens its snapshot after remount', async () => {
  const saved = { runId: 'run-1', status: 'passed', savedAt: '2026-11-04T01:00:00Z', caseReference: 'tag/api/case.json', output: 'actual_response={"status":200,"body":"saved response"}' }
  let stored = false
  api.mockImplementation(async (url, options) => {
    if (options?.method === 'POST') { stored = true; return saved }
    return url.includes('?') ? { items: stored ? [saved] : [] } : saved
  })
  const props = { projectRef: 'demo.json', caseReference: 'tag/api/case.json' }
  const view = render(<SavedCaseResults {...props} result={{ runId: 'run-1', status: 'passed' }} />)
  expect(await screen.findByText('저장한 실행 결과가 없습니다.')).not.toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '실행 결과 앱에 저장' }))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/api/runs/run-1/save', { method: 'POST' }))
  await screen.findByRole('status')
  view.unmount()
  render(<SavedCaseResults {...props} />)
  await screen.findByLabelText('저장 결과 선택')
  fireEvent.click(screen.getByText('저장 결과 보기 (1)'))
  expect(screen.getByLabelText('저장 결과 선택')).toBeVisible()
  fireEvent.change(screen.getByLabelText('저장 결과 선택'), { target: { value: 'run-1' } })
  await screen.findByText(/saved response/)
  expect(api.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
})
it('reports storage failures without claiming success', async () => {
  api.mockImplementation(async (url, options) => { if (options?.method === 'POST') throw new Error('저장소 오류'); return { items: [] } })
  render(<SavedCaseResults projectRef="demo.json" caseReference="tag/api/case.json" result={{ runId: 'run-1', status: 'error' }} />)
  fireEvent.click(screen.getByRole('button', { name: '실행 결과 앱에 저장' }))
  expect(await screen.findByRole('status')).toHaveTextContent('저장소 오류')
})
