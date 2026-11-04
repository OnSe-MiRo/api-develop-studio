import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it } from 'vitest'
import { ContractSummary, readContractSummary } from './ContractSummary.jsx'
import { RunResult } from './RunResult.jsx'
const digest='a'.repeat(64)
it('shows passed and failed metadata without rendering unrelated report fields',()=>{
  const view=render(<ContractSummary contract={{valid:true,issueCount:0,documentDigest:digest,body:'PRIVATE',token:'PRIVATE'}} />)
  expect(screen.getByText('OpenAPI 계약 통과')).toBeInTheDocument()
  expect(screen.getByText(/문제 0개/)).toBeInTheDocument()
  expect(screen.getByText('검사 명세 SHA-256')).toBeInTheDocument()
  expect(screen.getByText(digest)).toBeInTheDocument()
  expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument()
  view.rerender(<ContractSummary contract={{valid:false,issueCount:2,documentDigest:'b'.repeat(64)}} />)
  expect(screen.getByText('OpenAPI 계약 실패')).toBeInTheDocument()
  expect(screen.queryByText(digest)).not.toBeInTheDocument()
})
it('distinguishes absent summaries from invalid or contradictory metadata',()=>{
  expect(readContractSummary(undefined).state).toBe('missing')
  expect(readContractSummary(null).state).toBe('missing')
  for(const value of [true,[],{}, {valid:'false',issueCount:1,documentDigest:digest}, {valid:true,issueCount:1,documentDigest:digest}, {valid:false,issueCount:0,documentDigest:digest}, {valid:false,issueCount:101,documentDigest:digest}, {valid:true,issueCount:0,documentDigest:'PRIVATE'}, {valid:false,issueCount:-1,documentDigest:digest}, {valid:false,issueCount:1.5,documentDigest:digest}]) {
    expect(readContractSummary(value).state).toBe('invalid')
  }
  const view=render(<ContractSummary />)
  expect(screen.getByText('OpenAPI 계약 요약 없음')).toBeInTheDocument()
  view.rerender(<ContractSummary contract={{valid:true,issueCount:0,documentDigest:'PRIVATE'}} />)
  expect(screen.getByText('OpenAPI 계약 요약 확인 불가')).toBeInTheDocument()
  expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument()
})
it('keeps overall assertion failure separate from a passed contract and handles legacy targets',()=>{
  const view=render(<RunResult result={{status:'failed',exitCode:1,result:{targets:[{caseId:'case',status:'failed',errorCategory:'assertion_failed',contract:{valid:true,issueCount:0,documentDigest:digest}},{caseId:'legacy',status:'passed'}]}}} />)
  expect(screen.getByText('실행 실패',{exact:true})).toBeVisible()
  expect(screen.getByText('OpenAPI 계약 통과')).not.toBeVisible()
  fireEvent.click(screen.getByText('실행 상세 결과 보기'))
  expect(screen.getByText('OpenAPI 계약 통과')).toBeVisible()
  expect(screen.getByText('OpenAPI 계약 통과')).toBeInTheDocument()
  expect(screen.getByText('OpenAPI 계약 요약 없음')).toBeInTheDocument()
  expect(screen.getByText(/assertion_failed/)).toBeInTheDocument()
  view.rerender(<RunResult result={{status:'running',result:{targets:[]}}} />)
  expect(screen.queryByRole('group',{name:'OpenAPI 계약 결과'})).not.toBeInTheDocument()
  expect(screen.queryByText(digest)).not.toBeInTheDocument()
})
