import { Field } from './Field.jsx'

const authorizationTypes = ['No Auth', 'API Key', 'Bearer Token', 'JWT Bearer', 'Basic Auth', 'Digest Auth', 'OAuth 1.0', 'OAuth 2.0', 'Hawk Authentication', 'AWS Signature', 'NTLM Authentication', 'Akamai EdgeGrid', 'ASAP (Atlassian)']

const authorizationFields = {
  'API Key': [['key', 'Key'], ['value', 'Value', 'secret'], ['addTo', 'Add to', 'select', ['Header', 'Query Params']]],
  'Bearer Token': [['token', 'Token', 'secret']],
  'JWT Bearer': [['token', 'JWT Token', 'secret'], ['headerPrefix', 'Header Prefix'], ['addTo', 'Add JWT token to', 'select', ['Request Header', 'Query Params']], ['key', 'Query Key']],
  'Basic Auth': [['username', 'Username'], ['password', 'Password', 'secret']],
  'Digest Auth': [['username', 'Username'], ['password', 'Password', 'secret']],
  'OAuth 1.0': [['consumerKey', 'Consumer Key'], ['consumerSecret', 'Consumer Secret', 'secret'], ['accessToken', 'Access Token', 'secret'], ['tokenSecret', 'Token Secret', 'secret'], ['signatureMethod', 'Signature Method', 'select', ['HMAC-SHA256', 'HMAC-SHA1', 'PLAINTEXT']], ['realm', 'Realm'], ['callback', 'Callback URL'], ['verifier', 'Verifier']],
  'OAuth 2.0': [['token', 'Access Token', 'secret'], ['headerPrefix', 'Header Prefix'], ['addTo', 'Add authorization data to', 'select', ['Request Headers', 'Query Params']], ['key', 'Query Key']],
  'Hawk Authentication': [['id', 'Hawk Auth ID'], ['key', 'Hawk Auth Key', 'secret'], ['algorithm', 'Algorithm', 'select', ['sha256', 'sha1']], ['user', 'User'], ['ext', 'ext']],
  'AWS Signature': [['accessKey', 'Access Key'], ['secretKey', 'Secret Key', 'secret'], ['region', 'AWS Region'], ['service', 'Service Name'], ['sessionToken', 'Session Token', 'secret']],
  'NTLM Authentication': [['username', 'Username'], ['password', 'Password', 'secret'], ['domain', 'Domain'], ['workstation', 'Workstation']],
  'Akamai EdgeGrid': [['accessToken', 'Access Token', 'secret'], ['clientToken', 'Client Token', 'secret'], ['clientSecret', 'Client Secret', 'secret']],
  'ASAP (Atlassian)': [['token', 'JWT Token', 'secret'], ['headerPrefix', 'Header Prefix']],
}

function AuthorizationEditor({ type, values, onTypeChange, onValueChange }) {
  const fields = authorizationFields[type] || []
  return <div className="auth-form">
    <Field label="Type">
      <select value={type} onChange={event => onTypeChange(event.target.value)} aria-label="인증 타입">
        {authorizationTypes.map(value => <option key={value} value={value}>{value}</option>)}
      </select>
    </Field>
    {fields.length > 0 && <div className="auth-fields">{fields.map(([key, label, kind, options]) => <Field key={key} label={label} wide>
      {kind === 'select'
        ? <select value={values[key] || options[0]} onChange={event => onValueChange(key, event.target.value)}>{options.map(option => <option key={option} value={option}>{option}</option>)}</select>
        : <input type={kind === 'secret' ? 'password' : 'text'} value={values[key] || ''} onChange={event => onValueChange(key, event.target.value)} />}
    </Field>)}</div>}
    {type === 'No Auth' && <p className="hint">Authorization 정보를 요청에 추가하지 않습니다.</p>}
    {type === 'NTLM Authentication' && <p className="hint">NTLM은 서버와의 인증 핸드셰이크를 수행합니다. 실행 환경에 <code>requests-ntlm</code> 패키지가 필요합니다.</p>}
  </div>
}

export { authorizationTypes, AuthorizationEditor }
