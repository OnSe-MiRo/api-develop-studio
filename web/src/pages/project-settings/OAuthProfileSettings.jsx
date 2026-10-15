import { useMemo, useState } from 'react'
import { Field } from '../../components/Field.jsx'
import { OAuthProfileStatus } from '../../components/OAuthProfileStatus.jsx'

const blank = () => ({ grantType: 'client_credentials', clientId: '', clientSecret: '', tokenUrl: '', authorizationUrl: '', scopes: '', clientAuthMethod: 'basic', issuer: '' })
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const parseObject = (text, label) => {
  try {
    const parsed = JSON.parse(text)
    return record(parsed) ? { value: parsed } : { error: `${label}은 JSON 객체여야 합니다.` }
  } catch { return { error: `${label} JSON을 먼저 수정하세요.` } }
}
const oauthForm = profile => ({
  grantType: profile?.grantType || 'client_credentials',
  clientId: profile?.clientId || '',
  clientSecret: profile?.clientSecret || '',
  tokenUrl: profile?.tokenUrl || '',
  authorizationUrl: profile?.authorizationUrl || '',
  scopes: Array.isArray(profile?.scopes) ? profile.scopes.join(' ') : '',
  clientAuthMethod: profile?.clientAuthMethod || 'basic',
  issuer: profile?.issuer || '',
})
const validHttpUrl = value => {
  try { return ['http:', 'https:'].includes(new URL(value).protocol) } catch { return false }
}

function OAuthProfileSettings({
  projectReference, authProfilesText, environmentsText, savedProjectForm,
  secretVariables, onAuthProfilesChange, onEnvironmentsChange,
}) {
  const [environment, setEnvironment] = useState('')
  const [selectedName, setSelectedName] = useState('')
  const [newName, setNewName] = useState('')
  const [draft, setDraft] = useState(blank)
  const [notice, setNotice] = useState('')
  const authResult = useMemo(() => parseObject(authProfilesText, '인증 프로필'), [authProfilesText])
  const envResult = useMemo(() => parseObject(environmentsText, '환경 프로필'), [environmentsText])
  const scopedEnvironment = environment && record(envResult.value?.[environment]) ? envResult.value[environment] : null
  const scopedProfiles = environment && record(scopedEnvironment?.auth_profiles) ? scopedEnvironment.auth_profiles : {}
  const profiles = environment ? { ...authResult.value, ...scopedProfiles } : authResult.value || {}
  const names = Object.entries(profiles).filter(([, profile]) => profile?.type === 'OAuth 2.0').map(([name]) => name)
  const selectedProfile = selectedName ? profiles[selectedName] : null
  const draftDirty = Boolean(selectedName && selectedProfile && JSON.stringify(draft) !== JSON.stringify(oauthForm(selectedProfile)))
  const saved = Boolean(projectReference && savedProjectForm && !draftDirty)
  const envSecrets = environment ? Object.entries(envResult.value?.[environment]?.variables?.secret || {}).filter(([, definition]) => definition?.configured || definition?.value).map(([name]) => name) : []
  const secretNames = [...new Set([...secretVariables.filter(item => item.name && (item.value || item.configured)).map(item => item.name), ...envSecrets])]
  const set = (key, value) => { setDraft(current => ({ ...current, [key]: value })); setNotice('') }
  const select = name => { setSelectedName(name); setNewName(''); setDraft(name ? oauthForm(profiles[name]) : blank()); setNotice('') }
  const selectEnvironment = name => { setEnvironment(name); setSelectedName(''); setNewName(''); setDraft(blank()); setNotice('') }
  const apply = () => {
    try {
      if (authResult.error || envResult.error) throw new Error(authResult.error || envResult.error)
      if (environment && !scopedEnvironment) throw new Error('선택한 환경 프로필 구조를 확인하세요.')
      const name = (selectedName || newName).trim()
      if (!/^[A-Za-z][A-Za-z0-9._-]*$/.test(name)) throw new Error('프로필 이름은 영문자로 시작하고 영문자·숫자·점·밑줄·하이픈만 사용하세요.')
      if (!selectedName && Object.hasOwn(profiles, name)) throw new Error('이미 사용 중인 프로필 이름입니다.')
      if (!draft.clientId.trim()) throw new Error('Client ID를 입력하세요.')
      if (draft.grantType === 'client_credentials' && draft.clientAuthMethod === 'none') throw new Error('Client Credentials에는 Client Secret 인증이 필요합니다.')
      if (!validHttpUrl(draft.tokenUrl)) throw new Error('Token URL은 HTTP 또는 HTTPS 절대 주소여야 합니다.')
      if (draft.grantType === 'authorization_code' && !validHttpUrl(draft.authorizationUrl)) throw new Error('Authorization URL은 HTTP 또는 HTTPS 절대 주소여야 합니다.')
      if (draft.issuer && !validHttpUrl(draft.issuer)) throw new Error('Issuer는 HTTP 또는 HTTPS 절대 주소여야 합니다.')
      if (draft.clientAuthMethod !== 'none' && !secretNames.some(secret => draft.clientSecret === `{{project.${secret}}}`)) throw new Error('Client Secret에 암호화 프로젝트 변수 참조를 선택하세요.')
      const profile = {
        type: 'OAuth 2.0', grantType: draft.grantType, clientId: draft.clientId.trim(), tokenUrl: draft.tokenUrl.trim(),
        scopes: [...new Set(draft.scopes.split(/\s+/).filter(Boolean))], clientAuthMethod: draft.clientAuthMethod,
        ...(draft.clientAuthMethod === 'none' ? {} : { clientSecret: draft.clientSecret }),
        ...(draft.grantType === 'authorization_code' ? { authorizationUrl: draft.authorizationUrl.trim() } : {}),
        ...(draft.issuer ? { issuer: draft.issuer.trim() } : {}),
      }
      if (environment) {
        const environments = structuredClone(envResult.value)
        environments[environment] = { ...environments[environment], auth_profiles: { ...scopedProfiles, [name]: profile } }
        onEnvironmentsChange(JSON.stringify(environments, null, 2))
      } else onAuthProfilesChange(JSON.stringify({ ...authResult.value, [name]: profile }, null, 2))
      setSelectedName(name); setNewName(''); setNotice('OAuth 프로필을 아래 JSON 설정에 적용했습니다. 프로젝트를 저장한 뒤 연결하세요.')
    } catch (error) { setNotice(error.message) }
  }
  const remove = () => {
    if (!selectedName || !selectedProfile) return
    if (environment) {
      const environments = structuredClone(envResult.value)
      const next = { ...scopedProfiles }; delete next[selectedName]
      environments[environment] = { ...environments[environment], auth_profiles: next }
      onEnvironmentsChange(JSON.stringify(environments, null, 2))
    } else {
      const next = { ...authResult.value }; delete next[selectedName]
      onAuthProfilesChange(JSON.stringify(next, null, 2))
    }
    select(''); setNotice('프로필을 JSON 설정에서 제거했습니다. 프로젝트 저장 후 반영됩니다.')
  }
  return <section className="card oauth-profile-settings" aria-label="OAuth 2.0 프로필 설정">
    <h4>OAuth 2.0 프로필</h4>
    <p className="hint">Client Secret은 아래 암호화 프로젝트 변수에서 선택합니다. 발급된 token과 인증 코드는 프로젝트 JSON에 저장되지 않습니다.</p>
    {(authResult.error || envResult.error) ? <p role="alert" className="notice">{authResult.error || envResult.error}</p> : <>
      <div className="form-grid project-settings-grid">
        <Field label="설정 범위"><select value={environment} onChange={event => selectEnvironment(event.target.value)}><option value="">프로젝트 공통</option>{Object.keys(envResult.value).map(name => <option key={name} value={name}>환경: {name}</option>)}</select></Field>
        <Field label="기존 OAuth 프로필"><select value={selectedName} onChange={event => select(event.target.value)}><option value="">새 프로필</option>{names.map(name => <option key={name} value={name}>{name}</option>)}</select></Field>
        {!selectedName && <Field label="새 프로필 이름"><input value={newName} onChange={event => setNewName(event.target.value)} placeholder="serviceLogin" /></Field>}
        <Field label="Grant"><select value={draft.grantType} onChange={event => setDraft(current => ({ ...current, grantType: event.target.value, clientAuthMethod: event.target.value === 'client_credentials' && current.clientAuthMethod === 'none' ? 'basic' : current.clientAuthMethod }))}><option value="client_credentials">Client Credentials</option><option value="authorization_code">Authorization Code + PKCE (S256)</option></select></Field>
        <Field label="Client ID"><input value={draft.clientId} onChange={event => set('clientId', event.target.value)} autoComplete="off" /></Field>
        <Field label="Token URL"><input type="url" value={draft.tokenUrl} onChange={event => set('tokenUrl', event.target.value)} placeholder="https://idp.example/token" /></Field>
        {draft.grantType === 'authorization_code' && <Field label="Authorization URL"><input type="url" value={draft.authorizationUrl} onChange={event => set('authorizationUrl', event.target.value)} placeholder="https://idp.example/authorize" /></Field>}
        <Field label="Client 인증 방식"><select value={draft.clientAuthMethod} onChange={event => set('clientAuthMethod', event.target.value)}><option value="basic">Basic</option><option value="post">POST body</option>{draft.grantType === 'authorization_code' && <option value="none">공개 Client (Secret 없음)</option>}</select></Field>
        {draft.clientAuthMethod !== 'none' && <Field label="Client Secret 변수"><select value={draft.clientSecret} onChange={event => set('clientSecret', event.target.value)}><option value="">암호화 변수 선택</option>{secretNames.map(name => <option key={name} value={`{{project.${name}}}`}>{name}</option>)}</select></Field>}
        <Field label="Scopes (공백 구분)"><input value={draft.scopes} onChange={event => set('scopes', event.target.value)} placeholder="read write" /></Field>
        <Field label="Issuer (선택)"><input type="url" value={draft.issuer} onChange={event => set('issuer', event.target.value)} placeholder="https://idp.example" /></Field>
      </div>
      <div className="actions"><button className="ghost" onClick={apply}>프로필을 JSON 설정에 적용</button>{selectedName && (!environment || Object.hasOwn(scopedProfiles, selectedName)) && <button className="danger-button" onClick={remove}>프로필 설정 제거</button>}</div>
      {environment && selectedName && !Object.hasOwn(scopedProfiles, selectedName) && <p className="hint">프로젝트 공통 프로필을 상속합니다. 이 환경에서 적용하면 override가 생성됩니다.</p>}
      {notice && <p role="status" className="notice">{notice}</p>}
      {selectedName && selectedProfile?.type === 'OAuth 2.0' && <OAuthProfileStatus key={`${environment}:${selectedName}`} projectRef={projectReference} name={selectedName} environment={environment} profile={selectedProfile} actions enabled={saved} />}
    </>}
  </section>
}

export { OAuthProfileSettings }
