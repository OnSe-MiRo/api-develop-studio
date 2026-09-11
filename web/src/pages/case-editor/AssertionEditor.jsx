import { Field } from '../../components/Field.jsx'
import { typeLabel, assertionOperators, assertionTypes, stringFormats, stringFormatLabel, assertionCanConfirm, assertionSummary } from '../../utils/studio.js'
import { useEffect, useState } from 'react'
import '../../format-menu.css'

function StringFormatPicker({ assertion, onUpdate }) {
  const selectedFormat = assertion.format || 'none'
  const [open, setOpen] = useState(false)
  const selectedLabel = stringFormatLabel(selectedFormat)
  const [query, setQuery] = useState(selectedLabel)
  useEffect(() => setQuery(selectedLabel), [selectedLabel])
  const normalizedQuery = query.trim().toLowerCase()
  const matches = stringFormats.filter(([value, label]) => !normalizedQuery || value.includes(normalizedQuery) || label.toLowerCase().includes(normalizedQuery))
  const selectFormat = value => {
    onUpdate('format', value)
    setOpen(false)
  }
  const handleQueryChange = event => {
    const nextQuery = event.target.value
    setQuery(nextQuery)
    setOpen(true)
    if (!nextQuery.trim()) {
      onUpdate('format', 'none')
    }
  }
  const handleBlur = () => {
    setOpen(false)
    if (!query.trim()) {
      onUpdate('format', 'none')
      setQuery(stringFormatLabel('none'))
    } else {
      setQuery(stringFormatLabel(assertion.format || 'none'))
    }
  }
  const selectFirstMatch = event => {
    if (event.key !== 'Enter') return
    event.preventDefault()
    if (!query.trim()) {
      selectFormat('none')
    } else if (matches.length) {
      selectFormat(matches[0][0])
    }
  }
  const handleFocus = () => {
    setOpen(true)
    setQuery('')
    onUpdate('format', 'none')
  }
  return <div className="format-control field">
    <span>format</span>
    <div className="format-combobox">
      <input
        className="format-input"
        aria-label="format"
        placeholder=""
        value={query}
        onFocus={handleFocus}
        onChange={handleQueryChange}
        onBlur={handleBlur}
        onKeyDown={selectFirstMatch}
      />
      {open && <div className="format-menu" role="listbox" aria-label="format 목록">
        {matches.length ? matches.map(([value, label]) => (
          <button
            type="button"
            role="option"
            aria-selected={value === selectedFormat}
            className={value === selectedFormat ? 'selected' : ''}
            key={value}
            onMouseDown={event => {
              event.preventDefault()
              selectFormat(value)
            }}
          >
            {label}
          </button>
        )) : <p>검색 결과가 없습니다.</p>}
      </div>}
    </div>
    {selectedFormat === 'custom' && <Field label="정규식"><input aria-label="정규식" value={assertion.pattern} placeholder="예: ^[A-Z]{3}-\\d{4}$" onChange={event => onUpdate('pattern', event.target.value)} /></Field>}
  </div>
}

function AssertionEditor({ assertions, variables, enabled, onAdd, onUpdate, onConfirm, onSelectVariable, onRemove }) {
  return <div className={`assertion-builder ${enabled ? '' : 'inactive'}`}>
    <div className="assertion-heading"><div><div className="assertion-title"><strong>변수별 조건 설정</strong><span className={`method-status ${enabled ? 'enabled' : ''}`}>{enabled ? '실행 대상' : '실행 제외'}</span></div><p className="hint">{variables.length ? `기대 응답에서 ${variables.length}개 변수를 찾았습니다. ` : '기대 응답 JSON을 입력하면 변수를 자동으로 찾습니다. '}각 변수에 독립적인 조건을 등록할 수 있습니다.{enabled ? ' 등록한 모든 조건을 만족해야 통과합니다.' : ' 설정은 보존되지만 현재 실행에서는 검사하지 않습니다.'}</p></div><button className="ghost" onClick={onAdd}>＋ 변수 조건 추가</button></div>
    {assertions.length ? <div className="assertion-list">{assertions.map((assertion, index) => {
      const rangeOperator = assertion.operator === 'between' || assertion.operator === 'length_between'
      const valueOperator = ['gt', 'gte', 'lt', 'lte'].includes(assertion.operator)
      const selectedVariable = variables.find(variable => variable.path === assertion.path)
      if (assertion.confirmed) return <div className="assertion-summary-row" key={index}>
        <div className="assertion-summary"><span className="assertion-check">✓</span><span><small>응답 변수 {index + 1}</small><strong>{assertionSummary(assertion)}</strong></span></div>
        <div className="assertion-summary-actions"><button className="ghost" onClick={() => onUpdate(index, 'confirmed', false)}>수정</button><button className="icon danger" aria-label={`${index + 1}번째 조건 삭제`} title="조건 삭제" onClick={() => onRemove(index)}>×</button></div>
      </div>
      return <div className="assertion-row" key={index}>
        <div className="assertion-target"><Field label={`응답 변수 ${index + 1}`}><select value={selectedVariable?.path || '__custom__'} onChange={event => { const variable = variables.find(item => item.path === event.target.value); onSelectVariable(index, variable) }}><option value="__custom__">직접 경로 입력</option>{variables.map(variable => <option key={variable.path} value={variable.path}>{variable.path} · {typeLabel(variable.type)} · {variable.example}</option>)}</select></Field>{selectedVariable ? <small>{typeLabel(selectedVariable.type)} 변수 · 예시 {selectedVariable.example}</small> : <Field label="직접 경로"><input value={assertion.path} placeholder="body.age 또는 body.items.0" onChange={event => onUpdate(index, 'path', event.target.value)} /></Field>}</div>
        <Field label="조건"><select value={assertion.operator} onChange={event => onUpdate(index, 'operator', event.target.value)}>{assertionOperators.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        {rangeOperator ? <div className="assertion-range"><Field label="최솟값"><input type="number" min={assertion.operator === 'length_between' ? '0' : undefined} step={assertion.operator === 'length_between' ? '1' : 'any'} value={assertion.min} onChange={event => onUpdate(index, 'min', event.target.value)} /></Field><Field label="최댓값"><input type="number" min={assertion.operator === 'length_between' ? '0' : undefined} step={assertion.operator === 'length_between' ? '1' : 'any'} value={assertion.max} onChange={event => onUpdate(index, 'max', event.target.value)} /></Field>{assertion.operator === 'between' && <div className="assertion-boundaries"><label><input type="checkbox" checked={assertion.includeMin} onChange={event => onUpdate(index, 'includeMin', event.target.checked)} />최솟값 포함</label><label><input type="checkbox" checked={assertion.includeMax} onChange={event => onUpdate(index, 'includeMax', event.target.checked)} />최댓값 포함</label></div>}</div> : assertion.operator === 'type' ? <div className="type-condition"><Field label="데이터 타입"><select value={assertion.value || 'number'} onChange={event => onUpdate(index, 'value', event.target.value)}>{assertionTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>{assertion.value === 'string' && <StringFormatPicker assertion={assertion} onUpdate={(key, value) => onUpdate(index, key, value)} />}</div> : valueOperator ? <Field label="기준값"><input type="number" step="any" value={assertion.value} onChange={event => onUpdate(index, 'value', event.target.value)} /></Field> : <div className="assertion-no-value">추가 값 없이 경로만 검사합니다.</div>}
        <div className="assertion-row-actions"><button className="icon assertion-confirm" aria-label={`${index + 1}번째 조건 확인`} title={assertionCanConfirm(assertion) ? '입력 완료 및 조건 검증 활성화' : '조건 값을 모두 올바르게 입력하세요.'} disabled={!assertionCanConfirm(assertion)} onClick={() => onConfirm(index)}>✓</button><button className="icon danger" aria-label={`${index + 1}번째 조건 삭제`} title="조건 삭제" onClick={() => onRemove(index)}>×</button></div>
      </div>
    })}</div> : <div className="assertion-empty">등록된 조건이 없습니다. 기존 기대 응답 값 비교만 실행됩니다.</div>}
  </div>
}

export { AssertionEditor }
