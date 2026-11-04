"""Non-secret environment metadata frozen alongside a release's OpenAPI source."""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re

SENSITIVE = re.compile(r'authorization|cookie|token|secret|password|api[-_]?key|credential',re.I)


def public_server(value):
    if not isinstance(value,str) or len(value)>4096 or any(ord(c)<32 for c in value):return None
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname:return None
        authority=parsed.netloc.rsplit('@',1)[-1]
        query=urlencode([(key,'[REDACTED]' if SENSITIVE.search(key) else item) for key,item in parse_qsl(parsed.query,keep_blank_values=True)])
        return urlunsplit((parsed.scheme,authority,parsed.path,query,''))
    except ValueError:return None


def portal_metadata(project):
    servers=[]
    def add(name,value):
        url=public_server(value)
        if url:servers.append({'name':str(name)[:120],'url':url})
    add('프로젝트 기본',project.get('base_url'))
    for server in project.get('base_urls',[]) if isinstance(project.get('base_urls'),list) else []:
        if isinstance(server,dict):add('Base URL: '+str(server.get('name','')),server.get('url'))
    for name,environment in (project.get('environments') or {}).items() if isinstance(project.get('environments'),dict) else []:
        if isinstance(environment,dict):add('환경: '+str(name),environment.get('base_url'))
    return {'servers':servers}
