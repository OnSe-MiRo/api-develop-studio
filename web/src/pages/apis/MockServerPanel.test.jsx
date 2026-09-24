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

it('clears an example when its media type or status changes', async () => {
  const mockOperations = [{
    id: 'GET /health', method: 'GET', path: '/health', editable: { operationId: 'health' },
    responses: [
      { status: 200, mock_content: {
        'application/json': { examples: ['second'] },
        'text/plain': { examples: ['plain'] },
      } },
      { status: 500, mock_content: { 'application/json': { examples: ['failure'] } } },
    ],
  }]
  api.mockResolvedValue({
    status: 'running', host: '127.0.0.1', port: 8880, url: 'http://127.0.0.1:8880',
    seed: 42, scenario: 'default', defaultLatencyMs: 0, activeOperations: 1,
    requestCount: 0, overrides: {},
  })

  render(<MockServerPanel projectRef="test.json" project={{ mockOperations }} />)
  await screen.findByText('실행 중')
  fireEvent.change(screen.getByRole('combobox', { name: '대상 Operation' }), { target: { value: 'health' } })
  const status = screen.getByRole('combobox', { name: '상태 코드 (Status)' })
  const media = screen.getByRole('combobox', { name: '미디어 타입 (Media Type)' })
  const example = screen.getByRole('combobox', { name: 'Example 이름' })

  fireEvent.change(media, { target: { value: 'application/json' } })
  fireEvent.change(example, { target: { value: 'second' } })
  fireEvent.change(media, { target: { value: 'text/plain' } })
  expect(example).toHaveValue('')
  fireEvent.click(screen.getByRole('button', { name: '오버라이드 적용' }))
  fireEvent.click(screen.getByRole('button', { name: '설정 적용' }))
  await waitFor(() => {
    const configCall = api.mock.calls.find(([path]) => path.endsWith('/mock/config'))
    expect(JSON.parse(configCall[1].body).overrides.health).toEqual({ mediaType: 'text/plain' })
  })

  fireEvent.change(media, { target: { value: 'application/json' } })
  fireEvent.change(example, { target: { value: 'second' } })
  fireEvent.change(status, { target: { value: '500' } })
  expect(media).toHaveValue('')
  expect(example).toHaveValue('')
  fireEvent.click(screen.getByRole('button', { name: '오버라이드 적용' }))
  expect(screen.getByRole('row', { name: /health 500 기본 -/ })).toBeInTheDocument()
})
