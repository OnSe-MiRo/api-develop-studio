import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { SchemaFields } from './OpenApiFields.jsx'

it('preserves a boolean schema and permits editing it as a boolean', () => {
  const onChange = vi.fn()
  render(<SchemaFields schema={false} version="3.1.0" onChange={onChange} />)
  expect(screen.getByText('Boolean schema: false')).toBeInTheDocument()
  fireEvent.click(screen.getByText('Schema 고급 JSON 편집'))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'true' } })
  expect(onChange).toHaveBeenCalledWith(true)
})

it('keeps 3.1 union type, falsey enum members, and empty string examples', () => {
  const onChange = vi.fn()
  render(<SchemaFields schema={{ type: ['string', 'null'], enum: [false, 0, null, ''], example: '' }} version="3.1.0" onChange={onChange} />)
  expect(screen.getByLabelText('타입')).toHaveValue('["string","null"]')
  expect(screen.queryByText('nullable (OpenAPI 3.0)')).not.toBeInTheDocument()
  expect(screen.getByLabelText('enum JSON')).toHaveValue('[\n  false,\n  0,\n  null,\n  ""\n]')
  fireEvent.change(screen.getByLabelText('example JSON'), { target: { value: '"next"' } })
  fireEvent.change(screen.getByLabelText('example JSON'), { target: { value: '""' } })
  expect(onChange).toHaveBeenCalledWith({ type: ['string', 'null'], enum: [false, 0, null, ''], example: '' })
})

it('retains 3.0 nullable and boolean exclusive minimum until edited', () => {
  const onChange = vi.fn()
  render(<SchemaFields schema={{ type: 'number', nullable: true, exclusiveMinimum: true, minimum: 0 }} version="3.0.3" onChange={onChange} />)
  expect(screen.getByLabelText('nullable (OpenAPI 3.0)')).toBeChecked()
  expect(screen.getByLabelText('exclusiveMinimum')).toBeChecked()
  fireEvent.change(screen.getByLabelText('minimum'), { target: { value: '1' } })
  expect(onChange).toHaveBeenCalledWith({ type: 'number', nullable: true, exclusiveMinimum: true, minimum: 1 })
})

it('removes the last required property instead of emitting required empty array', () => {
  const onChange = vi.fn()
  render(<SchemaFields schema={{ type: 'object', properties: { id: { type: 'string' } }, required: ['id'] }} version="3.0.3" onChange={onChange} />)
  fireEvent.click(screen.getByLabelText('required'))
  expect(onChange).toHaveBeenCalledWith({ type: 'object', properties: { id: { type: 'string' } } })
})

it('selects a 3.0 schema reference through allOf when extensions must survive', () => {
  const onChange = vi.fn()
  render(<SchemaFields schema={{ type: 'object', properties: { id: { type: 'string' } }, required: ['id'], 'x-owner': 'team' }} version="3.0.3" refs={[{ name: 'Pet', file: 'openapi.json', ref: '#/components/schemas/Pet' }]} onChange={onChange} />)
  fireEvent.change(screen.getAllByLabelText('Schema 참조')[0], { target: { value: '#/components/schemas/Pet' } })
  expect(onChange).toHaveBeenCalledWith({ 'x-owner': 'team', allOf: [{ $ref: '#/components/schemas/Pet' }] })
})

it('wraps a 3.0 reference when title and example must survive', () => {
  const onChange = vi.fn()
  render(<SchemaFields schema={{ type: 'string', title: 'Animal', example: 'Ada' }} version="3.0.3" refs={[{ name: 'Pet', file: 'openapi.json', ref: '#/components/schemas/Pet' }]} onChange={onChange} />)
  fireEvent.change(screen.getByLabelText('Schema 참조'), { target: { value: '#/components/schemas/Pet' } })
  expect(onChange).toHaveBeenCalledWith({ title: 'Animal', example: 'Ada', allOf: [{ $ref: '#/components/schemas/Pet' }] })
})
