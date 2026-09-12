import packageJson from '../../package.json'

function StudioShell({ tab, activeProject, error, onNavigate, onRefresh, children }) {
  const isApiCallTab = tab === 'api-call'
  const isDashboardTab = tab === 'dashboard'
  return <>
    <header className="topbar">
      <div className="brand"><img className="brand-logo" src="/logo.png" alt="API Develop Studio" /><div><strong>API Develop Studio</strong><span className="brand-version">v{packageJson.version}</span></div></div>
      <nav>
        <button className={isApiCallTab ? 'selected' : ''} onClick={() => onNavigate({ tab: 'api-call', activeProject })}>API 호출</button>
        <button className={!isApiCallTab && !isDashboardTab ? 'selected' : ''} onClick={() => onNavigate({ tab: 'project', activeProject })}>프로젝트</button>
        <button className={isDashboardTab ? 'selected' : ''} onClick={() => onNavigate({ tab: 'dashboard', activeProject: '' })}>대시보드</button>
      </nav>
      <button className="ghost refresh" onClick={onRefresh}>↻ 새로고침</button>
    </header>
    {error && <div className="connection-error" role="alert">{error} — Python 서버를 먼저 실행하세요: <code>python3 react_server.py</code></div>}
    {children}
  </>
}

export { StudioShell }
