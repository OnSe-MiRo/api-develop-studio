import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { ReferencePicker } from './ReferencePicker.jsx'
import { api } from '../utils/studio.js'

vi.mock('../utils/studio.js', () => ({ api: vi.fn() }))
beforeEach(() => { api.mockReset() })

function Picker() {
  const [value, setValue] = useState('saved.json')
  return <ReferencePicker resource="cases" project="demo.json" label="케이스" placeholder="선택" value={value} onChange={setValue} />
}

it('keeps the selected reference while paging and resets the cursor for submitted search', async () => {
  api.mockImplementation(async url => {
    const query = new URL(url, 'https://local.test').searchParams
    expect(query.get('page_size')).toBe('20')
    expect(query.get('project')).toBe('demo.json')
    if (query.get('q')) {
      expect(query.get('q')).toBe('한글+')
      expect(query.has('cursor')).toBe(false)
      return { items: ['search.json'] }
    }
    return query.get('cursor') === 'next' ? { items: ['second.json'], previousCursor: 'prev' } : { items: ['first.json'], nextCursor: 'next' }
  })
  render(<Picker />)
  await screen.findByRole('option', { name: 'first.json' })
  fireEvent.click(screen.getByRole('button', { name: '케이스 다음 선택지' }))
  await screen.findByRole('option', { name: 'second.json' })
  expect(screen.getByLabelText('케이스')).toHaveValue('saved.json')
  fireEvent.change(screen.getByLabelText('케이스'), { target: { value: 'second.json' } })
  const search = screen.getByLabelText('케이스 선택지 검색어')
  fireEvent.change(search, { target: { value: ' 한글+ ' } })
  fireEvent.keyDown(search, { key: 'Enter' })
  await screen.findByRole('option', { name: 'search.json' })
  expect(screen.getByLabelText('케이스')).toHaveValue('second.json')
  expect(api).toHaveBeenCalledTimes(3)
})

it('ignores a cancelled response when the project changes', async () => {
  let finish, signal
  api.mockImplementation((url, options) => {
    if (url.includes('project=a.json')) {
      signal = options.signal
      return new Promise(resolve => { finish = resolve })
    }
    return Promise.resolve({ items: ['b-case'] })
  })
  const field = project => <ReferencePicker key={project} resource="cases" project={project} label="케이스" value="" onChange={() => {}} />
  const view = render(field('a.json'))
  view.rerender(field('b.json'))
  await screen.findByRole('option', { name: 'b-case' })
  expect(signal.aborted).toBe(true)
  await act(async () => finish({ items: ['a-case'] }))
  expect(screen.queryByRole('option', { name: 'a-case' })).not.toBeInTheDocument()
})
