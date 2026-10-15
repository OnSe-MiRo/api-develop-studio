import { useEffect, useState } from 'react'
import { api } from '../../utils/studio.js'
import { OAuthProfileStatus } from '../../components/OAuthProfileStatus.jsx'

function PipelineAuthStatus({ projectRef, project, environment, caseRefs, refreshKey = null }) {
  const [cases, setCases] = useState([])
  const [error, setError] = useState('')
  const references = [...new Set(caseRefs.filter(Boolean))].sort()
  const referenceKey = references.join('\n')
  useEffect(() => {
    let active = true
    setCases([]); setError('')
    if (!projectRef || !referenceKey) return undefined
    Promise.all(references.map(async reference => {
      const document = await api(`/api/cases/${encodeURIComponent(reference)}`)
      return { reference, profile: document.request?.auth_profile || '' }
    })).then(result => { if (active) setCases(result) }).catch(issue => { if (active) setError(issue.message) })
    return () => { active = false }
  }, [projectRef, referenceKey])
  if (!referenceKey) return null
  const profiles = { ...project?.auth_profiles, ...project?.environments?.[environment]?.auth_profiles }
  return <section className="card pipeline-auth-status" aria-label="파이프라인 단계 인증">
    <h3>단계 인증 프로필</h3>
    <p className="hint">파이프라인은 각 케이스에 저장된 인증 프로필 참조를 실행 환경에 맞춰 사용합니다.</p>
    {error && <p role="alert" className="notice">케이스 인증 정보를 불러오지 못했습니다: {error}</p>}
    {!error && !cases.length && <p className="hint">케이스 인증 정보를 불러오는 중…</p>}
    {cases.map(item => <div className="pipeline-auth-case" key={item.reference}>
      <strong>{item.reference}</strong><span>{item.profile || '직접 설정'}</span>
      {item.profile && <OAuthProfileStatus projectRef={projectRef} name={item.profile} environment={environment} profile={profiles[item.profile]} refreshKey={refreshKey} />}
    </div>)}
  </section>
}

export { PipelineAuthStatus }
