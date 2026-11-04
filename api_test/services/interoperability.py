"""Preview and individually apply sanitized requests through revisioned storage."""
from copy import deepcopy
import hashlib
import json
import re

from api_test.interoperability import ImportError, parse_import, export_curl
from api_test.request_profiles import select_environment
from urllib.parse import urlsplit


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def slug(value):
    return re.sub(r'[^a-z0-9_-]+', '-', str(value).lower()).strip('-')[:60] or 'imported'


def preview_data(body, studio):
    store = studio.collaboration_store()
    reference = body.get('project')
    if not isinstance(reference, str): raise studio.ApiError('프로젝트를 선택하세요.')
    studio.ensure_example_project_enabled(reference)
    current = store.get('projects', reference)
    if current is None: raise studio.ApiError('프로젝트를 찾을 수 없습니다.', 404)
    studio.ensure_example_document_writable('projects', reference, current.document)
    try:
        parsed = parse_import(body.get('format'), body.get('source'))
    except ImportError as exc:
        raise studio.ApiError(str(exc)) from exc
    tag=body.get('tag','imported')
    if not isinstance(tag,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,59}',tag):
        raise studio.ApiError('저장 태그는 소문자·숫자로 시작하는 60자 이하 영문/숫자/_/- 이어야 합니다.')
    items=[]
    for index, imported in enumerate(parsed['items']):
        target=f"{tag}/{slug(imported['name'])}-{digest(reference)[:8]}-{index+1}/{body['format']}.json"
        existing=store.get('cases', target)
        conflict=existing is not None
        blocked=conflict and existing.document.get('project') != reference
        document={'name':imported['name'], 'project':reference,'request':imported['request'],'expected':{'status':200}}
        item={'index':index,'reference':target,'document':document,'expectedRevision':existing.revision if existing else 0,
              'conflict':conflict,'blocked':blocked, 'projectRevision':current.revision}
        item['digest']=digest(item)
        items.append(item)
    environment=None
    if parsed['environment'] is not None:
        incoming=parsed['environment']; name=slug(incoming['name'])
        previous=current.document.get('environments',{}).get(name)
        secret=(previous or {}).get('variables',{}).get('secret',{})
        incoming_plain=incoming['variables']['plain']
        blocked=bool(set(incoming_plain) & set(secret))
        # Never expose existing encrypted values or unrelated variables in preview.
        environment={'name':name,'plain':incoming_plain,'conflict':previous is not None,'blocked':blocked,
                     'projectRevision':current.revision}
        environment['digest']=digest(environment)
    return {'items':items,'environment':environment,'warnings':parsed['warnings'],
            'projectRevision':current.revision},current


def preview(request, studio):
    result,_=preview_data(request.read_body(),studio)
    return request.json_response(200,result)


def apply_import(request, studio):
    body=request.read_body()
    result,project=preview_data(body,studio)
    environment=result['environment']
    if environment is not None:
        item=environment
    else:
        index=body.get('index')
        if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<len(result['items']):
            raise studio.ApiError('가져올 항목을 선택하세요.')
        item=result['items'][index]
    if body.get('digest') != item['digest']:
        raise studio.ApiError('원본 또는 저장 상태가 변경됐습니다. 미리보기를 다시 확인하세요.',409)
    if item['blocked']:
        raise studio.ApiError('다른 프로젝트의 케이스 또는 기존 secret 변수와 충돌합니다.',409)
    if item['conflict'] and body.get('overwrite') is not True:
        raise studio.ApiError('기존 항목과 충돌합니다. 덮어쓰기를 명시적으로 선택하세요.',409)
    store=studio.collaboration_store()
    if environment is not None:
        document=deepcopy(project.document)
        name=environment['name']
        env=document.setdefault('environments',{}).setdefault(name,{'base_url':document.get('base_url','')})
        env.setdefault('variables',{}).setdefault('plain',{}).update(environment['plain'])
        env['variables'].setdefault('secret',{})
        stored=store.save('projects',body['project'],document,expected_revision=project.revision,actor_id=request.actor_id())
        return request.json_response(200,{'reference':body['project'],'revision':stored.revision,'kind':'environment'})
    document=studio.normalize_case_document(item['document'])
    studio.validate_project_reference(document)
    stored=store.save('cases',item['reference'],document,expected_revision=item['expectedRevision'],actor_id=request.actor_id())
    return request.json_response(200,{'reference':item['reference'],'revision':stored.revision,'kind':'case'})


def export(request, studio):
    body=request.read_body()
    reference=body.get('reference')
    if not isinstance(reference,str): raise studio.ApiError('케이스를 선택하세요.')
    current=studio.collaboration_store().get('cases',reference)
    if current is None: raise studio.ApiError('케이스를 찾을 수 없습니다.',404)
    raw=deepcopy(current.document.get('request',{}))
    try:
        # Relative case URLs need their stored project origin; never resolve secrets.
        if isinstance(raw.get('url'),str) and not urlsplit(raw['url']).scheme and not raw['url'].startswith('{{'):
            project=studio.collaboration_store().get('projects',current.document.get('project',''))
            if project is None: raise studio.ApiError('프로젝트를 찾을 수 없습니다.',404)
            effective=select_environment(project.document)
            base_url=effective.get('base_url','')
            selected=current.document.get('base_url_name') if not effective.get('default_environment') else None
            if selected:
                base_url=next((value['url'] for value in effective.get('base_urls',[]) if value['name']==selected),None)
                if base_url is None: raise studio.ApiError('케이스의 Base URL을 찾을 수 없습니다.')
            raw['url']=base_url.rstrip('/')+'/'+raw['url'].lstrip('/')
        result=export_curl(raw)
    except (ImportError, TypeError, ValueError, AttributeError) as exc:
        raise studio.ApiError(str(exc) if isinstance(exc,ImportError) else '내보낼 요청 구조를 확인하세요.') from exc
    return request.json_response(200,result)
