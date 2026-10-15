"""OIDC browser endpoints and the COL-2 verified CurrentUser adapter."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit, urlencode

from cryptography.fernet import Fernet, InvalidToken
from starlette.responses import JSONResponse, RedirectResponse

from api_test.database import LOCAL_CONTEXT, RequestContext, database_url
from api_test.identity_store import IdentityStore, TOKEN
from api_test.oidc_client import LoginError, OidcClient, Settings, origin
from api_test.request_scope import CurrentUser

_CACHE_LOCK=threading.Lock()


class Authentication:
    def __init__(self,settings,store,client=None):
        self.settings=settings;self.store=store;self.client=client or OidcClient(settings)
        self.cipher=Fernet(settings.session_key.encode())
        self.csrf_key=base64.urlsafe_b64decode(settings.session_key)
        self._begins=threading.BoundedSemaphore(4)

    def csrf(self,token):
        return base64.urlsafe_b64encode(hmac.new(self.csrf_key,('csrf\0'+token).encode(),hashlib.sha256).digest()).decode().rstrip('=')

    def validate_host(self,request):
        try:host=origin(urlsplit(self.settings.public_url).scheme+'://'+request.headers.get('host',''))
        except LoginError as exc:raise LoginError('invalid_public_host',403) from exc
        if host!=origin(self.settings.public_url):raise LoginError('invalid_public_host',403)

    def session(self,request,*,csrf=False,require_workspace=True):
        self.validate_host(request)
        token=request.cookies.get(self.settings.cookie_name,'')
        result=self.store.session(token,self.settings.fingerprint,self.settings.idle_seconds,require_workspace=require_workspace)
        if csrf:
            try:
                supplied_origin=request.headers.get('origin','')
                parsed=urlsplit(supplied_origin)
                valid_origin=not parsed.path and not parsed.query and not parsed.fragment and origin(supplied_origin)==origin(self.settings.public_url)
            except (LoginError,ValueError):valid_origin=False
            supplied=request.headers.get('x-csrf-token','')
            if not valid_origin or not TOKEN.fullmatch(supplied) or not hmac.compare_digest(supplied,self.csrf(token)):
                raise LoginError('csrf_rejected',403)
        return token,result

    def current_user(self,request):
        _,session=self.session(request,csrf=request.method not in ('GET','HEAD','OPTIONS'))
        return CurrentUser(session['userId'],session['workspace']['id'])

    def begin(self,request):
        if not self._begins.acquire(False):raise LoginError('login_capacity_exceeded',429)
        try:return self._begin(request)
        finally:self._begins.release()

    def _begin(self,request):
        self.validate_host(request)
        binding=request.cookies.get(self.settings.state_cookie,'')
        if not TOKEN.fullmatch(binding):binding=secrets.token_urlsafe(32)
        state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
        location=self.client.authorization_url(state,nonce,verifier)
        payload=self.cipher.encrypt(json.dumps({'nonce':nonce,'verifier':verifier}).encode()).decode()
        self.store.save_state(state,binding,self.settings.fingerprint,payload)
        response=RedirectResponse(location,status_code=303)
        response.set_cookie(self.settings.state_cookie,binding,max_age=600,httponly=True,secure=self.settings.secure,samesite='lax',path='/')
        return secure_response(response)

    def callback(self,request):
        self.validate_host(request)
        for key in ('state','code','error'):
            if len(request.query_params.getlist(key))>1:raise LoginError('invalid_oidc_callback',401)
        encrypted=self.store.consume_state(request.query_params.get('state'),request.cookies.get(self.settings.state_cookie,''),self.settings.fingerprint)
        if request.query_params.get('error'):raise LoginError('provider_login_denied',401)
        try:pending=json.loads(self.cipher.decrypt(encrypted.encode(),ttl=600))
        except (InvalidToken,ValueError,KeyError) as exc:raise LoginError('login_state_invalid',401) from exc
        identity=self.client.redeem(request.query_params.get('code'),pending['nonce'],pending['verifier'])
        token=self.store.start_session(identity['issuer'],identity['subject'],self.settings.fingerprint,self.settings.idle_seconds,self.settings.absolute_seconds,request.cookies.get(self.settings.cookie_name))
        response=RedirectResponse(origin(self.settings.public_url)+'/projects',status_code=303)
        response.delete_cookie(self.settings.state_cookie,path='/',secure=self.settings.secure,httponly=True,samesite='lax')
        response.set_cookie(self.settings.cookie_name,token,max_age=self.settings.absolute_seconds,httponly=True,secure=self.settings.secure,samesite='lax',path='/')
        return secure_response(response)

    def info(self,request):
        token,session=self.session(request,require_workspace=False)
        return {'mode':'remote','authenticated':True,'loginAvailable':True,'csrfToken':self.csrf(token),**session}


def secure_response(response):
    response.headers['Cache-Control']='private, no-store'
    response.headers['Vary']='Cookie, Authorization'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="frame-ancestors 'none'"
    return response


def service(request,studio):
    injected=getattr(request.app.state,'authentication',None)
    if injected is not None:return injected
    try:settings=Settings.from_env()
    except (LoginError,OSError,TypeError,ValueError) as exc:raise LoginError('oidc_not_configured',503) from exc
    path=Path(os.environ.get('STUDIO_DB_PATH',studio.ROOT/'data'/'studio.db'))
    key=(settings.fingerprint,str(path),database_url())
    with _CACHE_LOCK:
        cache=getattr(request.app.state,'authentication_cache',None)
        if cache is None:cache={};request.app.state.authentication_cache=cache
        if key not in cache:
            if len(cache)>=4:cache.clear()
            cache[key]=Authentication(settings,IdentityStore(path))
        return cache[key]


def auth_call(request,studio,callback):
    try:return callback(service(request.request,studio))
    except LoginError as exc:raise studio.ApiError(exc.code,exc.status_code) from exc
    except PermissionError as exc:raise studio.ApiError('workspace_access_denied',403) from exc


def login_start(request,studio):return auth_call(request,studio,lambda auth:auth.begin(request.request))


def login_callback(request,studio):
    try:return auth_call(request,studio,lambda auth:auth.callback(request.request))
    except studio.ApiError as exc:
        # Never echo provider errors, codes, state, ID tokens or query strings.
        try:
            auth=service(request.request,studio)
            response=RedirectResponse(origin(auth.settings.public_url)+'/projects?'+urlencode({'loginError':str(exc)}),status_code=303)
        except LoginError:
            response=JSONResponse({'error':'oidc_not_configured','loginUrl':'/auth/login'},status_code=503)
        return secure_response(response)


def session_info(request,studio):
    if os.environ.get('STUDIO_AUTH_MODE','local')=='local' and getattr(request.request.app.state,'authentication',None) is None:
        host=urlsplit('http://'+request.headers.get('host','')).hostname
        if host not in ('127.0.0.1','localhost','::1'):raise studio.ApiError('local_loopback_required',403)
        store=studio.collaboration_store()
        from contextlib import closing
        from api_test.database import require_membership
        with closing(store.connect()) as db:role=require_membership(db,LOCAL_CONTEXT)
        return secure_response(request.json_response(200,{'mode':'local','authenticated':True,'loginAvailable':False,'userId':LOCAL_CONTEXT.user_id,'displayName':'로컬 사용자','workspace':{'id':LOCAL_CONTEXT.workspace_id,'name':'Local workspace','role':role},'workspaces':[],'csrfToken':None}))
    try:
        auth=service(request.request,studio)
        try:payload=auth.info(request.request)
        except LoginError as exc:
            if exc.code in ('session_required','session_expired'):payload={'mode':'remote','authenticated':False,'loginAvailable':True}
            else:raise
        return secure_response(request.json_response(200,payload))
    except LoginError as exc:
        if exc.code=='oidc_not_configured':return secure_response(request.json_response(200,{'mode':'remote','authenticated':False,'loginAvailable':False,'error':'oidc_not_configured'}))
        raise studio.ApiError(exc.code,exc.status_code) from exc


def logout(request,studio):
    def operation(auth):
        token,_=auth.session(request.request,csrf=True,require_workspace=False)
        auth.store.logout(token,auth.settings.fingerprint,auth.settings.idle_seconds)
        response=request.json_response(200,{'loggedOut':True})
        response.delete_cookie(auth.settings.cookie_name,path='/',secure=auth.settings.secure,httponly=True,samesite='lax')
        return secure_response(response)
    return auth_call(request,studio,operation)


def select_workspace(request,studio):
    def operation(auth):
        token,_=auth.session(request.request,csrf=True,require_workspace=False)
        auth.store.switch_workspace(token,auth.settings.fingerprint,auth.settings.idle_seconds,request.read_body().get('workspaceId'))
        return secure_response(request.json_response(200,auth.info(request.request)))
    return auth_call(request,studio,operation)


def identity_call(request,studio,callback):
    path=Path(os.environ.get('STUDIO_DB_PATH',studio.ROOT/'data'/'studio.db'))
    try:return secure_response(request.json_response(200,callback(IdentityStore(path))))
    except LoginError as exc:raise studio.ApiError(exc.code,exc.status_code) from exc
    except PermissionError as exc:raise studio.ApiError('workspace_access_denied',403) from exc


def list_members(request,studio):
    return identity_call(request,studio,lambda store:{'items':store.members(request.context)})


def change_member(request,studio):
    def operation(store):
        body=request.read_body()
        store.change_member(request.context,body.get('userId'),body.get('role'),body.get('status'),body.get('reason'),body.get('revision'))
        return {'saved':True}
    return identity_call(request,studio,operation)


def audit_events(request,studio):
    def operation(store):
        try:limit=int(request.query_value('limit') or '50')
        except ValueError as exc:raise studio.ApiError('invalid_limit') from exc
        return store.events(request.context,before=request.query_value('before'),limit=limit)
    return identity_call(request,studio,operation)
