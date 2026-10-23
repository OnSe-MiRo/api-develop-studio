import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi, beforeEach } from 'vitest'
import { caseContractPayload } from './CaseContractSettings.jsx'
import { CaseEditor } from './CaseEditor.jsx'
import { api } from '../../utils/studio.js'
vi.mock('../../utils/studio.js', async original => ({...await original(),api:vi.fn()}))
vi.mock('../../hooks/useRunJob.js',()=>({useRunJob:()=>({result:null,setResult:vi.fn(),busy:false,start:vi.fn(),cancel:vi.fn()})}))
beforeEach(()=>vi.resetAllMocks())
it('keeps opt-out absent and validates optional contract fields without echoing values',()=>{
  expect(caseContractPayload({contractEnabled:false,contractVariables:'bad'})).toEqual({})
  expect(caseContractPayload({contractEnabled:true,contractVariables:'{"version":"v2"}',contractDocumentUrl:'https://docs.test/spec'})).toEqual({contract_validation:{enabled:true,server_variables:{version:'v2'},document_url:'https://docs.test/spec'}})
  for(const value of ['[1]','{"v":1}','{"PRIVATE":']) expect(()=>caseContractPayload({contractEnabled:true,contractVariables:value})).toThrow(/계약 server 변수/)
  expect(()=>caseContractPayload({contractEnabled:true,contractDocumentUrl:'file:///PRIVATE'})).toThrow(/계약 문서 기준 URL/)
})
it('restores saved case settings and preserves them on save alongside assertions',async()=>{
  api.mockImplementation(async (url,options)=>options?.method==='PUT'?{_storage:{revision:2}}:{project:'demo.json',request:{method:'GET',url:'/items'},expected:{status:200},contract_validation:{enabled:true,server_variables:{version:'v2'},document_url:'https://docs.test/spec'},_storage:{revision:1}})
  render(<CaseEditor projectRef="demo.json" project={{base_url:'https://test'}} caseReference="tag/api/case.json" refresh={vi.fn()} />)
  await waitFor(()=>expect(screen.getByLabelText('저장된 프로젝트 명세로 응답 검증')).toBeChecked())
  expect(screen.getByLabelText('계약 server 변수 (JSON)')).toHaveValue(JSON.stringify({version:'v2'},null,2))
  expect(screen.getByLabelText('계약 문서 기준 URL')).toHaveValue('https://docs.test/spec')
  fireEvent.click(screen.getByRole('button',{name:'저장',exact:true}))
  await waitFor(()=>expect(api.mock.calls.some(([,o])=>o?.method==='PUT')).toBe(true))
  const payload=JSON.parse(api.mock.calls.find(([,o])=>o?.method==='PUT')[1].body)
  expect(payload.contract_validation).toEqual({enabled:true,server_variables:{version:'v2'},document_url:'https://docs.test/spec'})
  expect(payload.expected.status).toBe(200);expect(payload._storage.revision).toBe(1)
})
it('turning off contract checking removes settings from the saved document',async()=>{
  api.mockImplementation(async (url,options)=>options?.method==='PUT'?{_storage:{revision:2}}:{project:'demo.json',request:{method:'GET',url:'/items'},expected:{status:200},contract_validation:{enabled:true},_storage:{revision:1}})
  render(<CaseEditor projectRef="demo.json" project={{base_url:'https://test'}} caseReference="tag/api/case.json" refresh={vi.fn()} />)
  await waitFor(()=>expect(screen.getByLabelText('저장된 프로젝트 명세로 응답 검증')).toBeChecked())
  fireEvent.click(screen.getByLabelText('저장된 프로젝트 명세로 응답 검증'))
  fireEvent.click(screen.getByRole('button',{name:'저장',exact:true}))
  await waitFor(()=>expect(api.mock.calls.some(([,o])=>o?.method==='PUT')).toBe(true))
  expect(JSON.parse(api.mock.calls.find(([,o])=>o?.method==='PUT')[1].body)).not.toHaveProperty('contract_validation')
})
