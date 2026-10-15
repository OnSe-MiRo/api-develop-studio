"""Configured OIDC code flow: bounded endpoint transport and explicit JWT validation."""
from dataclasses import dataclass, field
import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import math
import os
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit, urlencode, quote_plus, parse_qsl

import jwt
from cryptography.fernet import Fernet


class LoginError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status_code = code, status


def origin(value):
    if not isinstance(value,str):raise LoginError('invalid_oidc_url')
    try:
        parsed=urlsplit(value)
        if not isinstance(value,str) or len(value)>2048 or any(ord(c)<=32 or c=='\\' for c in value) or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
        host=parsed.hostname.encode('idna').decode().lower()
        host='['+host+']' if ':' in host else host
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        if not 1<=port<=65535:raise ValueError()
        return parsed.scheme+'://'+host+(':'+str(port) if port!=(443 if parsed.scheme=='https' else 80) else '')
    except (TypeError,ValueError,UnicodeError) as exc:
        raise LoginError('invalid_oidc_url') from exc


@dataclass(frozen=True)
class Settings:
    issuer: str
    client_id: str
    public_url: str
    session_key: str = field(repr=False)
    client_secret: str = field(default='',repr=False)
    auth_method: str = 'client_secret_basic'
    endpoint_origins: tuple = ()
    private_origins: tuple = ()
    allow_http: bool = False
    ca_file: str | None = None
    idle_seconds: int = 1800
    absolute_seconds: int = 28800

    def __post_init__(self):
        for value in (self.issuer,self.public_url):
            host_origin=origin(value)
            parsed=urlsplit(value)
            if parsed.query or parsed.fragment:raise LoginError('invalid_oidc_configuration')
            if parsed.scheme=='http' and not (self.allow_http and parsed.hostname in ('localhost','127.0.0.1','::1')):raise LoginError('oidc_https_required')
        if urlsplit(self.public_url).path not in ('','/'):raise LoginError('public_url_must_be_origin')
        if not self.client_id or len(self.client_id)>512 or self.auth_method not in ('client_secret_basic','client_secret_post','none'):raise LoginError('invalid_oidc_configuration')
        if self.auth_method!='none' and not self.client_secret:raise LoginError('oidc_client_secret_missing')
        if not 60<=self.idle_seconds<=86400 or not self.idle_seconds<=self.absolute_seconds<=604800:raise LoginError('invalid_session_lifetime')
        try:Fernet(self.session_key.encode())
        except (ValueError,UnicodeError) as exc:raise LoginError('invalid_session_key') from exc
        for value in (*self.endpoint_origins,*self.private_origins):
            if origin(value)!=value:raise LoginError('endpoint_allowlist_requires_origins')

    @classmethod
    def from_env(cls):
        def secret(name):
            filename=os.environ.get(name+'_FILE')
            if filename:
                from pathlib import Path
                return Path(filename).read_text().strip()
            return os.environ.get(name,'')
        return cls(issuer=os.environ.get('STUDIO_OIDC_ISSUER',''),client_id=os.environ.get('STUDIO_OIDC_CLIENT_ID',''),
            public_url=os.environ.get('STUDIO_PUBLIC_URL',''),session_key=secret('STUDIO_SESSION_KEY'),client_secret=secret('STUDIO_OIDC_CLIENT_SECRET'),
            auth_method=os.environ.get('STUDIO_OIDC_AUTH_METHOD','client_secret_basic'),
            endpoint_origins=tuple(os.environ.get('STUDIO_OIDC_ENDPOINT_ORIGINS','').split()),private_origins=tuple(os.environ.get('STUDIO_OIDC_PRIVATE_ORIGINS','').split()),
            allow_http=os.environ.get('STUDIO_OIDC_ALLOW_LOOPBACK_HTTP')=='true' and os.environ.get('LOCAL_SERVER')=='true',
            ca_file=os.environ.get('STUDIO_OIDC_CA_FILE') or None,idle_seconds=int(os.environ.get('STUDIO_SESSION_IDLE_SECONDS','1800')),absolute_seconds=int(os.environ.get('STUDIO_SESSION_MAX_SECONDS','28800')))

    @property
    def callback(self):return origin(self.public_url)+'/auth/callback'
    @property
    def secure(self):return self.public_url.startswith('https://')
    @property
    def cookie_name(self):return '__Host-studio_session' if self.secure else 'studio_session_dev'
    @property
    def state_cookie(self):return '__Host-studio_login' if self.secure else 'studio_login_dev'
    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps([self.issuer,self.client_id,self.public_url,self.session_key,self.client_secret,self.auth_method,self.endpoint_origins,self.private_origins,self.allow_http,self.ca_file,self.idle_seconds,self.absolute_seconds],sort_keys=True).encode()).hexdigest()


class Transport:
    def __init__(self,settings):self.settings=settings

    def json(self,url,*,form=None,headers=None,limit=512*1024):
        settings=self.settings;endpoint_origin=origin(url)
        if endpoint_origin not in {origin(settings.issuer),*settings.endpoint_origins}:raise LoginError('oidc_endpoint_not_allowed')
        parsed=urlsplit(url)
        if parsed.scheme=='http' and not (settings.allow_http and parsed.hostname in ('localhost','127.0.0.1','::1')):raise LoginError('oidc_https_required')
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        try:
            addresses=sorted({ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)},key=lambda address:(address.version,str(address)))
        except (OSError,ValueError) as exc:raise LoginError('oidc_dns_failed',502) from exc
        local=settings.allow_http and parsed.hostname in ('localhost','127.0.0.1','::1')
        if not addresses or not all(address.is_loopback if local else address.is_global or endpoint_origin in settings.private_origins for address in addresses):raise LoginError('oidc_address_not_allowed',502)
        connection=http.client.HTTPConnection(parsed.hostname,port,timeout=8)
        # This connection must only use the validated, pinned socket, including after timeout.
        connection.auto_open=0
        deadline=time.monotonic()+8
        timer=threading.Timer(8,lambda: self._abort(connection));timer.daemon=True;timer.start()
        try:
            connection.sock=socket.create_connection((str(addresses[0]),port),timeout=max(0.001,deadline-time.monotonic()))
            if parsed.scheme=='https':
                context=ssl.create_default_context(cafile=settings.ca_file)
                tls_socket=context.wrap_socket(connection.sock,server_hostname=parsed.hostname,do_handshake_on_connect=False)
                connection.sock=tls_socket
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError()
                tls_socket.settimeout(remaining)
                tls_socket.do_handshake()
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError()
            connection.sock.settimeout(remaining)
            payload=urlencode(form).encode('ascii') if form is not None else None
            outgoing={'Host':parsed.netloc,'Accept':'application/json','Cache-Control':'no-store',**(headers or {})}
            if form is not None:outgoing['Content-Type']='application/x-www-form-urlencoded'
            connection.request('POST' if form is not None else 'GET',(parsed.path or '/')+('?' + parsed.query if parsed.query else ''),body=payload,headers=outgoing)
            response=connection.getresponse()
            if response.status!=200 or response.getheader('Content-Type','').split(';')[0].strip().lower()!='application/json':raise LoginError('oidc_endpoint_rejected',502)
            data=bytearray()
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError()
                if connection.sock:connection.sock.settimeout(remaining)
                chunk=response.read1(min(8192,limit+1-len(data)))
                if not chunk:break
                data.extend(chunk)
                if len(data)>limit:raise LoginError('oidc_response_too_large',502)
            value=json.loads(data)
            if not isinstance(value,dict):raise LoginError('invalid_oidc_response',502)
            return value
        except (OSError,ValueError,RecursionError,http.client.HTTPException) as exc:
            if isinstance(exc,LoginError):raise
            raise LoginError('oidc_endpoint_unavailable',502) from exc
        finally:timer.cancel();connection.close()

    @staticmethod
    def _abort(connection):
        if connection.sock:
            try:connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()


class OidcClient:
    def __init__(self,settings,transport=None):
        self.settings=settings;self.transport=transport or Transport(settings)
        self._lock=threading.Lock();self._metadata=None;self._metadata_until=0
        self._keys=None;self._keys_until=0;self._last_key_fetch=0;self._keys_uri=None
        self._exchanges=threading.BoundedSemaphore(4)

    def metadata(self):
        with self._lock:
            if self._metadata and time.monotonic()<self._metadata_until:return self._metadata
            document=self.transport.json(self.settings.issuer.rstrip('/')+'/.well-known/openid-configuration')
            def supports(name,value,default=None):
                values=document.get(name,default or [])
                return isinstance(values,list) and value in values
            if document.get('issuer')!=self.settings.issuer or not supports('response_types_supported','code') or not supports('id_token_signing_alg_values_supported','RS256') or not supports('code_challenge_methods_supported','S256'):raise LoginError('unsupported_oidc_provider',503)
            if not supports('token_endpoint_auth_methods_supported',self.settings.auth_method,['client_secret_basic']):raise LoginError('unsupported_client_auth_method',503)
            for key in ('authorization_endpoint','token_endpoint','jwks_uri'):
                value=document.get(key)
                if origin(value) not in {origin(self.settings.issuer),*self.settings.endpoint_origins}:raise LoginError('oidc_endpoint_not_allowed')
                if urlsplit(value).scheme=='http' and not (self.settings.allow_http and urlsplit(value).hostname in ('localhost','127.0.0.1','::1')):raise LoginError('oidc_https_required')
            self._metadata=document;self._metadata_until=time.monotonic()+300
            return document

    def authorization_url(self,state,nonce,verifier):
        url=self.metadata()['authorization_endpoint']
        fields={'response_type':'code','client_id':self.settings.client_id,'redirect_uri':self.settings.callback,'scope':'openid','state':state,'nonce':nonce,'code_challenge_method':'S256','code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
        if set(dict(parse_qsl(urlsplit(url).query))) & set(fields):raise LoginError('invalid_authorization_endpoint')
        return url+('&' if urlsplit(url).query else '?')+urlencode(fields)

    def keys(self,uri,*,force=False):
        with self._lock:
            now=time.monotonic()
            if self._keys and self._keys_uri==uri and now<self._keys_until and (not force or now-self._last_key_fetch<10):return self._keys
            payload=self.transport.json(uri)
            keys=payload.get('keys')
            if not isinstance(keys,list) or not 1<=len(keys)<=50:raise LoginError('invalid_jwks',502)
            self._keys=keys;self._keys_uri=uri;self._keys_until=now+300;self._last_key_fetch=now
            return keys

    def redeem(self,code,nonce,verifier):
        if not isinstance(code,str) or not 1<=len(code)<=4096:raise LoginError('invalid_authorization_code')
        if not self._exchanges.acquire(False):raise LoginError('login_capacity_exceeded',429)
        try:
            metadata=self.metadata()
            fields={'grant_type':'authorization_code','code':code,'redirect_uri':self.settings.callback,'code_verifier':verifier,'client_id':self.settings.client_id}
            headers={}
            if self.settings.auth_method=='client_secret_basic':
                value=quote_plus(self.settings.client_id)+':'+quote_plus(self.settings.client_secret)
                headers['Authorization']='Basic '+base64.b64encode(value.encode()).decode();fields.pop('client_id')
            elif self.settings.auth_method=='client_secret_post':fields['client_secret']=self.settings.client_secret
            payload=self.transport.json(metadata['token_endpoint'],form=fields,headers=headers,limit=64*1024)
            if 'error' in payload or not isinstance(payload.get('access_token'),str) or not payload['access_token'] or str(payload.get('token_type','')).lower()!='bearer':raise LoginError('invalid_token_response',401)
            token=payload.get('id_token')
            if not isinstance(token,str) or len(token)>32768:raise LoginError('missing_id_token',401)
            try:
                header=jwt.get_unverified_header(token)
                if header.get('alg')!='RS256' or header.get('crit') or header.get('b64') is False or header.get('typ','JWT').upper()!='JWT':raise ValueError()
                kid=header.get('kid')
                if kid is not None and (not isinstance(kid,str) or len(kid)>256):raise ValueError()
                matches=[]
                for force in (False,True):
                    keys=self.keys(metadata['jwks_uri'],force=force)
                    matches=[key for key in keys if isinstance(key,dict) and key.get('kty')=='RSA' and key.get('use','sig')=='sig' and key.get('alg','RS256')=='RS256' and 'verify' in key.get('key_ops',['verify']) and (kid is None or key.get('kid')==kid)]
                    if len(matches)==1:break
                if len(matches)!=1:raise ValueError()
                key=jwt.PyJWK.from_dict(matches[0],algorithm='RS256').key
                if not 2048<=key.key_size<=8192:raise ValueError()
                claims=jwt.decode(token,key=key,algorithms=['RS256'],audience=self.settings.client_id,issuer=self.settings.issuer,leeway=30,options={'require':['iss','sub','aud','exp','iat','nonce']})
                if any(not isinstance(claims[name],(int,float)) or isinstance(claims[name],bool) or not math.isfinite(claims[name]) for name in ('exp','iat')):raise ValueError()
                if not isinstance(claims['sub'],str) or not 1<=len(claims['sub'])<=512 or claims['nonce']!=nonce:raise ValueError()
                if 'at_hash' in claims:
                    expected_hash=base64.urlsafe_b64encode(hashlib.sha256(payload['access_token'].encode('ascii')).digest()[:16]).decode().rstrip('=')
                    if not isinstance(claims['at_hash'],str) or not hmac.compare_digest(claims['at_hash'],expected_hash):raise ValueError()
                if claims.get('azp') is not None and claims['azp']!=self.settings.client_id:raise ValueError()
                if isinstance(claims['aud'],list) and len(claims['aud'])>1 and claims.get('azp')!=self.settings.client_id:raise ValueError()
                if not isinstance(claims['iat'],(int,float)) or isinstance(claims['iat'],bool) or time.time()-claims['iat']>600:raise ValueError()
                return {'issuer':claims['iss'],'subject':claims['sub']}
            except (jwt.PyJWTError,TypeError,ValueError,KeyError,AttributeError,OverflowError) as exc:
                raise LoginError('id_token_invalid',401) from exc
        finally:self._exchanges.release()
