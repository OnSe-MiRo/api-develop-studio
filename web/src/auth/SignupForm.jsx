import { useState } from 'react'

export function SignupForm({ onCancel }) {
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    const form = event.currentTarget
    const data = new FormData(form)
    const password = data.get('password')
    if (password !== data.get('confirmation')) { setError('비밀번호 확인이 일치하지 않습니다.'); return }
    setBusy(true)
    setError('')
    try {
      const response = await fetch('/auth/signup', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.get('email'), password }),
      })
      if (!response.ok) {
        const result = await response.json().catch(() => ({}))
        throw new Error(result.message || '가입 요청을 처리할 수 없습니다. 잠시 후 다시 시도하세요.')
      }
      form.reset()
      setDone(true)
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <main className="card login-card"><h1>회원가입</h1>
    {done ? <><p role="status">SSO 로그인에서 이메일과 비밀번호를 입력하세요.</p><a className="primary login-link" href="/auth/login">SSO 로그인</a></> :
      <form className="form-grid" onSubmit={submit}>
        <p>처음 로그인하면 개인 워크스페이스가 생성됩니다.</p>
        <label className="field">이메일<input type="email" name="email" required maxLength={254} autoComplete="email" /></label>
        <label className="field">비밀번호 (12자 이상)<input type="password" name="password" required minLength={12} autoComplete="new-password" /></label>
        <label className="field">비밀번호 확인<input type="password" name="confirmation" required autoComplete="new-password" /></label>
        {error && <p role="alert">{error}</p>}
        <div className="actions"><button className="primary" disabled={busy}>{busy ? '가입 중…' : '계정 만들기'}</button><button type="button" onClick={onCancel} disabled={busy}>돌아가기</button></div>
      </form>}
  </main>
}
