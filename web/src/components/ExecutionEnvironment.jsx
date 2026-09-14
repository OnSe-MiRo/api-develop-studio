import { Field } from './Field.jsx'
export function ExecutionEnvironment({ project, value, onChange }) {
  return <Field label="실행 환경"><select value={value} onChange={event => onChange(event.target.value)}><option value="">프로젝트 기본 환경</option>{Object.keys(project?.environments || {}).map(name => <option key={name}>{name}</option>)}</select></Field>
}
