function ProjectVariableRows({ secret = false, items, onAdd, onUpdate, onRemove }) {
  return <section className={`project-variable-group ${secret ? 'secret' : ''}`}>
    <div className="project-variable-heading"><div><strong>{secret ? '보안 변수' : '일반 변수'}</strong><p className="hint">{secret ? 'API Key·토큰처럼 노출되면 안 되는 값을 암호화해 저장합니다.' : '외부에 노출되어도 되는 프로젝트 공통값을 평문으로 저장합니다.'}</p></div><button className="ghost" onClick={onAdd}>＋ 변수 추가</button></div>
    {items.length ? <div className="project-variable-list"><div className="project-variable-header"><span>변수명</span><span>값</span><span /></div>{items.map((item, index) => <div className="project-variable-row" key={index}><input value={item.name} onChange={event => onUpdate(index, 'name', event.target.value)} placeholder={secret ? 'api_key' : 'tenant_id'} /><div className="project-variable-value"><input type={secret ? 'password' : 'text'} value={item.value} onChange={event => onUpdate(index, 'value', event.target.value)} placeholder={secret && item.configured ? '저장된 보안 값 유지' : '값 입력'} />{secret && item.configured && !item.value && <small>암호화된 값 저장됨</small>}</div><button className="icon danger" aria-label={`${index + 1}번째 ${secret ? '보안' : '일반'} 변수 삭제`} onClick={() => onRemove(index)}>×</button></div>)}</div> : <div className="project-variable-empty">등록된 {secret ? '보안' : '일반'} 변수가 없습니다.</div>}
  </section>
}

export { ProjectVariableRows }
