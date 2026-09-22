import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { MockServerPanel } from './MockServerPanel.jsx'
import { api } from '../../utils/studio.js'

vi.mock('../../utils/studio.js', () => ({ api: vi.fn() }))
afterEach(() => vi.clearAllMocks())

it('shows stopped status and starts mock server', async () => {
  api.mockResolvedValueOnce({
    status: 'stopped',
    host: '127.0.0.1',
    port: 8880,
    url: '',
    seed: 42,
    scenario: 'default',
    defaultLatencyMs: 0,
    activeOperations: 0,
    requestCount: 0,
  }).mockResolvedValueOnce({
    status: 'running',
    host: '127.0.0.1',
    port: 8880,
    url: 'http://127.0.0.1:8880',
    seed: 42,
    scenario: 'default',
    defaultLatencyMs: 0,
    activeOperations: 5,
    requestCount: 0,
  })

  render(<MockServerPanel projectRef="test.json" project={{ _storage: { revision: 1 } }} />)

  // Initially shows stopped
  await screen.findByText('중지됨')
  expect(screen.getByRole('button', { name: '서버 시작' })).toBeEnabled()

  // Click start server
  fireEvent.click(screen.getByRole('button', { name: '서버 시작' }))

  // Now shows running
  await screen.findByText('실행 중')
  expect(screen.getByText('http://127.0.0.1:8880')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '중지' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'State 초기화' })).toBeInTheDocument()
})
it('stops running mock server and triggers reset', async () => {
  api.mockResolvedValueOnce({
    status: 'running',
    host: '127.0.0.1',
    port: 8880,
    url: 'http://127.0.0.1:8880',
    seed: 42,
    scenario: 'default',
    defaultLatencyMs: 0,
    activeOperations: 5,
    requestCount: 10,
  }).mockResolvedValueOnce({
    status: 'reset',
    message: 'State reset',
  }).mockResolvedValueOnce({
    status: 'running',
    host: '127.0.0.1',
    port: 8880,
    url: 'http://127.0.0.1:8880',
    seed: 42,
    scenario: 'default',
    defaultLatencyMs: 0,
    activeOperations: 5,
    requestCount: 0,
  }).mockResolvedValueOnce({
    status: 'stopped',
    message: 'Stopped',
  }).mockResolvedValueOnce({
    status: 'stopped',
    host: '127.0.0.1',
    port: 8880,
    url: '',
    seed: 42,
    scenario: 'default',
    defaultLatencyMs: 0,
    activeOperations: 0,
    requestCount: 0,
  })

  render(<MockServerPanel projectRef="test.json" project={{ _storage: { revision: 1 } }} />)

  await screen.findByText('실행 중')

  // Reset
  fireEvent.click(screen.getByRole('button', { name: 'State 초기화' }))
  await screen.findByText('Mock Server State가 초기화되었습니다.')

  // Stop
  fireEvent.click(screen.getByRole('button', { name: '중지' }))
  await screen.findByText('중지됨')
})

it('configures operation overrides and sends them in config update', async () => {
  const mockOperations = [{
    id: 'GET /users', method: 'GET', path: '/users', editable: { operationId: 'listUsers' },
    responses: [
      { status: 200, mock_content: { 'application/json': { examples: [] } } },
      { status: 500, mock_content: {} },
    ],
  }]

  api.mockResolvedValueOnce({
    status: 'running',
    host: '127.0.0.1',
    port: 8880,
    url: 'http://127.0.0.1:8880',
    seed: 42,
    scenario: 'default',
    defaultLatencyMs: 0,
    activeOperations: 1,
    requestCount: 0,
    overrides: {},
  }).mockResolvedValueOnce({
    status: 'running',
    host: '127.0.0.1',
    port: 8880,
    url: 'http://127.0.0.1:8880',
    seed: 42,
    scenario: 'default',
    defaultLatencyMs: 0,
    activeOperations: 1,
    requestCount: 0,
    overrides: {
      listUsers: { status: 500, errorResponse: true },
    },
  })

  render(<MockServerPanel projectRef="test.json" project={{ mockOperations, _storage: { revision: 1 } }} />)

  await screen.findByText('실행 중')

  // Select operation
  const opSelect = screen.getByRole('combobox', { name: '대상 Operation' })
  fireEvent.change(opSelect, { target: { value: 'listUsers' } })

  // Select status 500
  const statusSelect = screen.getByRole('combobox', { name: '상태 코드 (Status)' })
  fireEvent.change(statusSelect, { target: { value: '500' } })

  // Check error response checkbox
  const errorCheckbox = screen.getByRole('checkbox', { name: '오류 시뮬레이션' })
  fireEvent.click(errorCheckbox)

  // Click override apply button
  fireEvent.click(screen.getByRole('button', { name: '오버라이드 적용' }))
  await screen.findByText("Operation 'listUsers' 오버라이드가 등록되었습니다. (설정 적용 버튼을 눌러 서버에 반영하세요)")

  // Click server config apply button
  fireEvent.click(screen.getByRole('button', { name: '설정 적용' }))

  await waitFor(() => {
    expect(api).toHaveBeenCalledWith(
      '/api/projects/test.json/mock/config',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"listUsers":{"status":500,"errorResponse":true}'),
      })
    )
  })
})
