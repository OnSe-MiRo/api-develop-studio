"""Bounded, non-executing imports and secret-filtered POSIX cURL export."""
from copy import deepcopy
import json
import re
import shlex
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_BYTES = 1024 * 1024
MAX_ITEMS = 100
SENSITIVE = re.compile(r'authorization|cookie|token|secret|password|passwd|api[-_]?key|credential', re.I)
VARIABLE = re.compile(r'\{\{([^{}]+)\}\}')
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')
METHOD = re.compile(r'^[A-Z]+$')
REDACTED = '[REDACTED]'


class ImportError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ImportError(message)


def variables(value):
    if isinstance(value, str):
        def replace(match):
            name = match[1]
            if name.startswith('project.'):
                require(bool(NAME.fullmatch(name[8:])), '지원하지 않는 변수 참조입니다.')
                return match[0]
            require(bool(NAME.fullmatch(name)), '동적 변수·스크립트 변수는 지원하지 않습니다.')
            return '{{project.' + name + '}}'
        return VARIABLE.sub(replace, value)
    return value


def clean_json(value, warnings, depth=0):
    require(depth < 64, '본문 중첩 깊이 한도를 초과했습니다.')
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if SENSITIVE.search(key):
                result[key] = REDACTED
                warnings.add('민감값 후보를 제거했습니다. 실행 전 안전한 변수로 대체하세요.')
            else:
                result[key] = clean_json(item, warnings, depth + 1)
        return result
    if isinstance(value, list):
        return [clean_json(item, warnings, depth + 1) for item in value]
    return variables(value)


def clean_url(url, warnings):
    require(isinstance(url, str) and not any(c in url for c in '\r\n\0'), '요청 URL을 확인하세요.')
    url = variables(url)
    try:
        parts = urlsplit(url)
        require(parts.scheme in ('http', 'https') or url.startswith('{{project.'), 'HTTP(S) URL 또는 프로젝트 변수 URL만 지원합니다.')
        require(bool(parts.netloc) or url.startswith('{{project.'), '요청 URL host가 필요합니다.')
        netloc = parts.netloc
        if '@' in netloc:
            netloc = netloc.rsplit('@', 1)[1]
            warnings.add('URL 사용자 인증 정보를 제거했습니다.')
        # Keep untouched query bytes unless a sensitive key must be replaced.
        query = re.sub(r'(^|&)([^=&]+)=([^&]*)', lambda m: m[1] + m[2] + '=' + (urlencode({'v': REDACTED})[2:] if SENSITIVE.search(parse_qsl(m[2] + '=x')[0][0]) else m[3]), parts.query)
        if query != parts.query:
            warnings.add('URL query의 민감값 후보를 제거했습니다.')
        return urlunsplit((parts.scheme, netloc, parts.path, query, ''))
    except (ValueError, IndexError) as exc:
        raise ImportError('요청 URL을 확인하세요.') from exc


def headers(rows, warnings):
    result = {}
    for row in rows:
        require(isinstance(row, dict), '헤더 형식을 확인하세요.')
        if row.get('disabled'):
            continue
        key, value = row.get('key', row.get('name')), row.get('value', '')
        require(isinstance(key, str) and isinstance(value, str) and bool(re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)), '헤더 이름을 확인하세요.')
        require(not any(c in value for c in '\r\n\0'), '헤더 줄바꿈은 지원하지 않습니다.')
        require(key.lower() not in {k.lower() for k in result}, '중복 헤더는 현재 요청 모델에서 지원하지 않습니다.')
        if SENSITIVE.search(key):
            warnings.add('인증·쿠키·민감 헤더를 제거했습니다.')
            continue
        if key.lower() in ('content-length', 'host', 'connection', 'transfer-encoding'):
            warnings.add('전송 시 계산하는 헤더를 제외했습니다.')
            continue
        result[key] = variables(value)
    return result


def sanitize(request, warnings):
    request = deepcopy(request)
    require(sum(key in request for key in ('body','text','form_data')) <= 1, '본문 형식을 하나만 선택하세요.')
    method = request.get('method', 'GET').upper()
    require(bool(METHOD.fullmatch(method)), 'HTTP method를 확인하세요.')
    result = {'method': method, 'url': clean_url(request.get('url'), warnings),
              'headers': headers([{'key': k, 'value': v} for k, v in request.get('headers', {}).items()], warnings)}
    if request.get('auth') or request.get('auth_profile'):
        warnings.add('인증 설정은 가져오거나 내보내지 않습니다. 저장 후 인증 프로필을 선택하세요.')
    if 'body' in request:
        result['body'] = clean_json(request['body'], warnings)
    elif 'text' in request:
        text = request['text']
        require(isinstance(text, str) and '\0' not in text, '문자열 본문을 확인하세요.')
        content_type = next((v for k, v in result['headers'].items() if k.lower() == 'content-type'), '')
        parsed_ok = True
        try:
            parsed = json.loads(text)
        except (ValueError, RecursionError):
            parsed_ok = False
        if parsed_ok:
            cleaned = clean_json(parsed, warnings)
            # Preserve wire bytes for an unchanged raw JSON body.
            result['text'] = text if cleaned == parsed else json.dumps(cleaned, ensure_ascii=False, separators=(',', ':'))
        elif 'application/x-www-form-urlencoded' in content_type:
            pairs = parse_qsl(text, keep_blank_values=True)
            clean = [(k, REDACTED if SENSITIVE.search(k) else variables(v)) for k, v in pairs]
            result['text'] = text if clean == pairs else urlencode(clean)
            if clean != pairs:
                warnings.add('폼 본문의 민감값 후보 또는 변수 참조를 정리했습니다.')
        else:
            result['text'] = ''
            warnings.add('구조를 확인할 수 없는 본문은 민감값 보호를 위해 비웠습니다.')
    if 'form_data' in request:
        result['headers'] = {k:v for k,v in result['headers'].items() if k.lower() != 'content-type'}
        result['form_data'] = []
        for item in request['form_data']:
            require(isinstance(item, dict) and isinstance(item.get('key'), str), '폼 필드를 확인하세요.')
            require(not item.get('file'), '파일 첨부는 가져오기·내보내기에서 지원하지 않습니다.')
            result['form_data'].append({'key': item['key'], 'value': REDACTED if SENSITIVE.search(item['key']) else variables(str(item.get('value', '')))})
            if SENSITIVE.search(item['key']):
                warnings.add('폼 본문의 민감값 후보를 제거했습니다.')
    return result


def curl_request(source, warnings):
    try:
        tokens = shlex.split(source.replace('\\\n', ''), posix=True)
    except ValueError as exc:
        raise ImportError('cURL 인용부호를 확인하세요.') from exc
    require(tokens and tokens.pop(0) == 'curl', 'curl로 시작하는 명령 하나를 입력하세요.')
    request = {'headers': {}}
    rows, data, urls = [], [], []
    method, get, head = None, False, False
    i = 0
    while i < len(tokens):
        token = tokens[i]; i += 1
        require(token not in (';', '&&', '||', '|', '>', '>>', '<', '&'), '셸 연결·리다이렉션은 지원하지 않습니다.')
        if token in ('-q', '--disable', '-g', '--globoff', '-s', '-S', '-sS', '--silent', '--show-error'):
            continue
        if token in ('-G', '--get'):
            get = True; continue
        if token in ('-I', '--head'):
            head = True; continue
        argument = None
        if token.startswith('--') and '=' in token:
            token, argument = token.split('=', 1)
        elif token[:2] in ('-X', '-H', '-d', '-u', '-b') and len(token) > 2:
            token, argument = token[:2], token[2:]
        if token in ('-X', '--request', '-H', '--header', '-d', '--data', '--data-raw', '--data-binary', '--url', '-u', '--user', '-b', '--cookie', '--form-string'):
            if argument is None:
                require(i < len(tokens), 'cURL 옵션 값이 누락됐습니다.')
                argument = tokens[i]; i += 1
            if token in ('-X', '--request'):
                method = argument
            elif token in ('-H', '--header'):
                key, separator, value = argument.partition(':')
                require(bool(separator), '이름: 값 형식의 헤더만 지원합니다.')
                rows.append({'key':key, 'value':value.strip()})
            elif token == '--form-string':
                key, separator, value = argument.partition('=')
                require(bool(key and separator), '폼 필드는 이름=값 형식이어야 합니다.')
                request.setdefault('form_data', []).append({'key': key, 'value': value})
            elif token in ('--url',):
                urls.append(argument)
            elif token in ('-u', '--user', '-b', '--cookie'):
                warnings.add('cURL 인증·쿠키 값을 제거했습니다.')
            else:
                require(token == '--data-raw' or not argument.startswith('@'), '로컬 파일을 읽는 cURL 본문은 지원하지 않습니다.')
                data.append(argument)
        else:
            require(not token.startswith('-'), '지원하지 않는 cURL 옵션입니다. 요청 의미를 바꾸지 않도록 가져오기를 중단했습니다.')
            urls.append(token)
    require(len(urls) == 1, '요청 URL 하나만 지원합니다.')
    request.update(method=method or ('HEAD' if head else 'GET' if get else 'POST' if data or request.get('form_data') else 'GET'), url=urls[0], headers=headers(rows, warnings))
    require(not (request.get('form_data') and (data or get or head)), '폼과 다른 본문 옵션은 함께 사용할 수 없습니다.')
    if data:
        text = '&'.join(data)
        if get:
            parts = urlsplit(request['url'])
            request['url'] = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query + ('&' if parts.query else '') + text, parts.fragment))
        else:
            request['text'] = text
            if not any(k.lower() == 'content-type' for k in request['headers']):
                request['headers']['Content-Type'] = 'application/x-www-form-urlencoded'
    return request


def postman_body(body, request, warnings):
    mode = body.get('mode')
    if mode == 'raw':
        request['text'] = body.get('raw', '')
        if body.get('options', {}).get('raw', {}).get('language') == 'json' and not any(k.lower() == 'content-type' for k in request['headers']):
            request['headers']['Content-Type'] = 'application/json'
    elif mode == 'urlencoded':
        request['text'] = urlencode([(row['key'], row.get('value', '')) for row in body.get('urlencoded', []) if not row.get('disabled')])
        request['headers']['Content-Type'] = 'application/x-www-form-urlencoded'
    elif mode == 'formdata':
        require(all(row.get('type', 'text') == 'text' for row in body.get('formdata', []) if not row.get('disabled')), 'Postman 파일 첨부는 지원하지 않습니다.')
        request['form_data'] = [{'key':row['key'], 'value':row.get('value','')} for row in body.get('formdata', []) if not row.get('disabled')]
    else:
        require(not mode, '지원하지 않는 Postman 본문 형식입니다.')


def parse_import(format, source):
    require(isinstance(source, str) and 0 < len(source.encode()) <= MAX_BYTES, '입력은 1 MiB 이하의 비어 있지 않은 문자열이어야 합니다.')
    warnings, items, environment = set(), [], None
    try:
        if format == 'curl':
            items.append(('curl-request', curl_request(source, warnings)))
        else:
            document = json.loads(source)
            require(isinstance(document, dict), 'JSON object가 필요합니다.')
            if format == 'postman':
                schema = document.get('info', {}).get('schema', '')
                require('/v2.1.0/' in schema or '/v2.0.0/' in schema, 'Postman Collection v2.0/2.1 형식이 필요합니다.')
                def visit(nodes, depth=0):
                    require(depth < 16 and isinstance(nodes, list), 'Collection 폴더 깊이 또는 형식을 확인하세요.')
                    for node in nodes:
                        require(isinstance(node, dict), 'Collection 항목을 확인하세요.')
                        if node.get('event') or node.get('auth'):
                            warnings.add('Postman script와 인증은 실행·저장하지 않습니다.')
                        if 'item' in node:
                            visit(node['item'], depth + 1)
                        elif 'request' in node:
                            raw = node['request']
                            if isinstance(raw, str): raw = {'url':raw}
                            require(isinstance(raw, dict), 'Postman request를 확인하세요.')
                            url = raw.get('url')
                            if isinstance(url, dict):
                                require(not url.get('variable'), 'Postman 경로 변수는 먼저 URL에 반영하세요.')
                                require(isinstance(url.get('raw'), str), 'Postman URL raw 필드가 필요합니다.')
                                # The structured enabled query list is authoritative when present.
                                raw_url = url['raw']
                                if 'query' in url:
                                    parts = urlsplit(raw_url)
                                    query = urlencode([(x['key'], x.get('value','')) for x in url['query'] if not x.get('disabled')], safe='{}')
                                    raw_url = urlunsplit((parts.scheme,parts.netloc,parts.path,query,parts.fragment))
                                url = raw_url
                            request={'method':raw.get('method','GET'),'url':url,'headers':headers(raw.get('header', []),warnings),'auth':raw.get('auth')}
                            if raw.get('body'): postman_body(raw['body'], request, warnings)
                            items.append((node.get('name', 'request'),request))
                            require(len(items) <= MAX_ITEMS, '한 번에 요청 100개까지 가져올 수 있습니다.')
                visit(document.get('item'))
                if document.get('event') or document.get('auth'): warnings.add('Collection script와 인증은 실행·저장하지 않습니다.')
                if document.get('variable'): warnings.add('Collection 변수 값은 자동 저장하지 않습니다. Environment로 별도 가져오세요.')
            elif format == 'har':
                entries = document.get('log', {}).get('entries')
                require(isinstance(entries,list) and len(entries) <= MAX_ITEMS, 'HAR entries는 100개 이하여야 합니다.')
                for index, entry in enumerate(entries):
                    raw = entry['request']
                    request={'method':raw['method'],'url':raw['url'],'headers':headers(raw.get('headers',[]), warnings)}
                    if raw.get('cookies'): warnings.add('HAR 쿠키와 응답 내용은 가져오지 않습니다.')
                    body=raw.get('postData')
                    if body:
                        require(not body.get('encoding'), '인코딩된 HAR 본문은 지원하지 않습니다.')
                        mime=body.get('mimeType','')
                        if not any(k.lower()=='content-type' for k in request['headers']): request['headers']['Content-Type']=mime
                        if mime.startswith('multipart/'):
                            require(all(not x.get('fileName') for x in body.get('params', [])), 'HAR 파일 첨부는 지원하지 않습니다.')
                            request['form_data']=[{'key':x['name'],'value':x.get('value','')} for x in body.get('params',[])]
                        else:
                            request['text']=body.get('text', urlencode([(x['name'],x.get('value','')) for x in body.get('params',[])]))
                    items.append((f'har-request-{index+1}',request))
            elif format == 'environment':
                rows=document.get('values')
                require(isinstance(rows,list) and len(rows)<=500, 'Postman Environment values를 확인하세요.')
                plain={}
                for row in rows:
                    if row.get('enabled') is False: continue
                    key, value = row.get('key'), row.get('value','')
                    require(isinstance(key,str) and NAME.fullmatch(key) and isinstance(value,str), 'Environment 변수 이름·문자열 값을 확인하세요.')
                    require(key not in plain, '중복 Environment 변수를 지원하지 않습니다.')
                    if SENSITIVE.search(key) or row.get('type')=='secret':
                        warnings.add('Environment의 민감값 후보와 secret 변수를 제외했습니다.'); continue
                    plain[key]=variables(value)
                environment={'name':document.get('name','imported'),'variables':{'plain':plain,'secret':{}}}
            else:
                raise ImportError('지원하지 않는 가져오기 형식입니다.')
        require(bool(items) or environment is not None, '가져올 요청이 없습니다.')
        return {'items':[{'name':str(name)[:120], 'request':sanitize(request,warnings)} for name,request in items], 'environment':environment, 'warnings':sorted(warnings)}
    except (KeyError, TypeError, AttributeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ImportError): raise
        raise ImportError('입력 구조가 지원 형식과 다릅니다. 원본은 저장되지 않았습니다.') from exc


def export_curl(request):
    warnings=set()
    request=sanitize(request,warnings)
    require(not VARIABLE.search(json.dumps(request)), '변수가 포함된 요청은 값을 안전하게 대체한 뒤 내보내세요. secret은 자동 해석하지 않습니다.')
    parts=['curl','--disable','--globoff','--request',shlex.quote(request['method']),'--url',shlex.quote(request['url'])]
    for key,value in request['headers'].items(): parts.extend(['--header',shlex.quote(key+': '+value)])
    if 'body' in request and request['body'] is not None:
        if not any(k.lower()=='content-type' for k in request['headers']): parts.extend(['--header',shlex.quote('Content-Type: application/json')])
        parts.extend(['--data-raw',shlex.quote(json.dumps(request['body'],ensure_ascii=False,separators=(',',':')))])
    elif 'text' in request:
        if not any(k.lower()=='content-type' for k in request['headers']): parts.extend(['--header',shlex.quote('Content-Type: text/plain')])
        parts.extend(['--data-raw',shlex.quote(request['text'])])
    for item in request.get('form_data', []):
        parts.extend(['--form-string', shlex.quote(item['key'] + '=' + item['value'])])
    return {'curl':' '.join(parts), 'warnings':sorted(warnings)}
