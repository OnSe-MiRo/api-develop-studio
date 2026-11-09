import packageJson from '../../package.json'

function StudioShell({ tab, managing = false, activeProject, error, onNavigate, onRefresh, sessionControls, children }) {
  const isApiCallTab = !managing && tab === 'api-call'
  const isDashboardTab = !managing && tab === 'dashboard'
  const isLoadTestTab = !managing && ['load-tests', 'load-test-result', 'load-test-compare'].includes(tab)
  const isProjectTab = !managing && !isApiCallTab && !isDashboardTab && !isLoadTestTab
  return <>
    <header className="topbar">
      <div className="brand"><img className="brand-logo" src="/logo.png" alt="API Develop Studio" /><div><strong>API Develop Studio</strong><span className="brand-version">v{packageJson.version}</span></div></div>
      <nav aria-label="주요 탐색">
        <button className={isApiCallTab ? 'selected' : ''} aria-current={isApiCallTab ? 'page' : undefined} onClick={() => onNavigate({ tab: 'api-call', activeProject })}>API 호출</button>
        <button className={isProjectTab ? 'selected' : ''} aria-current={isProjectTab ? 'page' : undefined} onClick={() => onNavigate({ tab: 'project', activeProject })}>프로젝트</button>
        <button className={isDashboardTab ? 'selected' : ''} aria-current={isDashboardTab ? 'page' : undefined} onClick={() => onNavigate({ tab: 'dashboard', activeProject: '' })}>대시보드</button>
        <button className={isLoadTestTab ? 'selected' : ''} aria-current={isLoadTestTab ? 'page' : undefined} onClick={() => onNavigate({ tab: 'load-tests' })}>부하테스트</button>
      </nav>
      {sessionControls}
      <button className="ghost refresh" onClick={onRefresh}>↻ 새로고침</button>
    </header>
    {error && <div className="connection-error" role="alert">{error} — Python 서버를 먼저 실행하세요: <code>python3 react_server.py</code></div>}
    {children}
  </>
}

export { StudioShell }
