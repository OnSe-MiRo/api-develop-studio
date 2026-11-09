import base64
import hashlib
import json
import os
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlencode
from unittest.mock import patch

import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from api_test.database import connect, RequestContext
from api_test.collaboration_store import CollaborationStore
from api_test.identity_store import IdentityStore
from api_test.oidc_client import Settings, OidcClient, LoginError
from api_test.login import Authentication
from api_test.main import create_app
from api_test.services import studio


def number(value):return base64.urlsafe_b64encode(value.to_bytes((value.bit_length()+7)//8,'big')).decode().rstrip('=')


class FakeProvider:
    def __init__(self,key):
        self.key=key;self.codes={};self.calls=[];self.override={}
        public=key.public_key().public_numbers()
        self.jwk={'kty':'RSA','kid':'test-key','use':'sig','alg':'RS256','n':number(public.n),'e':number(public.e)}
    def authorize(self,url,subject='alice-subject'):
        query=parse_qs(urlsplit(url).query)
        assert query['code_challenge_method']==['S256']
        code='code-'+str(len(self.codes))+'-'+str(time.time_ns())
        self.codes[code]={'nonce':query['nonce'][0],'challenge':query['code_challenge'][0],'subject':subject}
        return code,query['state'][0]
    def json(self,url,*,form=None,headers=None,limit=None):
        self.calls.append((url,form,headers))
        if url.endswith('/.well-known/openid-configuration'):
            return {'issuer':'https://issuer.example.test','authorization_endpoint':'https://issuer.example.test/authorize','token_endpoint':'https://issuer.example.test/token','jwks_uri':'https://issuer.example.test/jwks','response_types_supported':['code'],'id_token_signing_alg_values_supported':['RS256'],'code_challenge_methods_supported':['S256'],'token_endpoint_auth_methods_supported':['client_secret_basic','none']}
        if url.endswith('/jwks'):return {'keys':[self.jwk]}
        if url.endswith('/token'):
            record=self.codes.pop(form['code'])
            assert base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'].encode()).digest()).decode().rstrip('=')==record['challenge']
            assert form['redirect_uri']=='https://studio.example.test/auth/callback'
            assert headers['Authorization']=='Basic '+base64.b64encode(b'client:CLIENT_SECRET').decode()
            now=int(time.time())
            claims={'iss':'https://issuer.example.test','sub':record['subject'],'aud':'client','iat':now,'exp':now+300,'nonce':record['nonce'],'email':'never-authority@example.test','roles':['owner'],**self.override}
            return {'id_token':jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'}),'access_token':'ACCESS_TOKEN_DO_NOT_STORE','token_type':'Bearer','refresh_token':'REFRESH_TOKEN_DO_NOT_STORE'}
        raise AssertionError(url)


class OidcLoginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve();self.path=self.root/'studio.db'
        roots={key:self.root/key for key in ('projects','cases','pipelines')}
        for root in roots.values():root.mkdir()
        for key,value in {'ROOT':self.root,'PROJECT_ROOT':roots['projects'],'CASE_ROOT':roots['cases'],'PIPELINE_ROOT':roots['pipelines'],'_COLLABORATION_STORE':None}.items():self.enterContext(patch.object(studio,key,value))
        self.enterContext(patch.dict(os.environ,{'STUDIO_DB_PATH':str(self.path),'STUDIO_DATABASE_URL':'','STUDIO_DATABASE_URL_FILE':'','STUDIO_REDIS_URL':'','STUDIO_AUTH_MODE':'remote','LOCAL_SERVER':'false','EXAMPLE_PROJECT':'false','API_TEST_ENCRYPTION_KEY':Fernet.generate_key().decode(),'API_TEST_ENCRYPTION_URL':''}))
        self.store=IdentityStore(self.path)
        for user,subject,role in [('alice','alice-subject','owner'),('bob','bob-subject','viewer')]:
            self.store.provision(issuer='https://issuer.example.test',subject=subject,user_id=user,display_name=user.title(),workspace_id='team-a',workspace_name='Team A',role=role)
        self.store.provision(issuer='https://issuer.example.test',subject='alice-subject',user_id='alice',display_name='Alice',workspace_id='team-b',workspace_name='Team B',role='editor')
        for workspace in ('team-a','team-b'):
            documents=CollaborationStore(self.path,roots,context=RequestContext(workspace,'alice'));documents.initialize(False)
            documents.save('projects','same.json',{'name':workspace,'base_url':'https://example.test'})
        self.settings=Settings('https://issuer.example.test','client','https://studio.example.test',Fernet.generate_key().decode(),client_secret='CLIENT_SECRET')
        self.provider=FakeProvider(self.key)
        self.auth=Authentication(self.settings,self.store,OidcClient(self.settings,self.provider))
        self.app=create_app(studio);self.app.state.authentication=self.auth
        self.client=self.enterContext(TestClient(self.app,base_url=self.settings.public_url,follow_redirects=False))

    def begin(self,client=None,subject='alice-subject'):
        client=client or self.client
        response=client.get('/auth/login');self.assertEqual(response.status_code,303,response.text)
        code,state=self.provider.authorize(response.headers['location'],subject)
        return '/auth/callback?'+urlencode({'code':code,'state':state})
    def login(self,subject='alice-subject'):
        response=self.client.get(self.begin(subject=subject));self.assertEqual(response.status_code,303,response.text)
        self.assertNotIn('loginError',response.headers['location'])
        return self.client.get('/api/session').json()
    def headers(self,info):return {'Origin':self.settings.public_url,'X-CSRF-Token':info['csrfToken']}

    def test_public_signup_only_provisions_new_dex_local_subjects(self):
        subject = base64.urlsafe_b64encode(b"\x0a\x27signup-" + b"a" * 32 + b"\x12\x05local").decode()
        with self.assertRaises(LoginError):
            self.store.start_session(self.settings.issuer, subject, 'config', 300, 600)
        with patch.dict(os.environ, {'STUDIO_DEX_SELF_SIGNUP':'true'}):
            self.assertTrue(self.client.get('/api/session').json()['signupAvailable'])
            info = self.login(subject)
            self.assertEqual([item['role'] for item in info['workspaces']], ['owner'])
            self.assertTrue(info['workspace']['id'].startswith('personal-'))
            self.assertEqual(self.login(subject)['workspace']['id'], info['workspace']['id'])
            self.assertEqual(self.login('alice-subject')['workspace']['id'], 'team-a')
            with self.assertRaises(LoginError):
                self.store.start_session(self.settings.issuer, 'unprovisioned', 'config', 300, 600, dex_signup=True)
            with self.store.connection() as db, db:
                db.execute("UPDATE users SET status='disabled' WHERE id=?", (info['userId'],))
            with self.assertRaises(LoginError):
                self.store.start_session(self.settings.issuer, subject, 'config', 300, 600, dex_signup=True)

    def test_login_rotation_private_cookie_and_no_tokens_in_storage(self):
        first=self.login();token=self.client.cookies.get(self.settings.cookie_name)
        self.assertEqual(first['userId'],'alice');self.assertEqual(first['workspace']['id'],'team-a')
        self.assertEqual(self.client.get('/api/projects/same.json').json()['name'],'team-a')
        callback=self.begin();response=self.client.get(callback)
        self.assertIn('HttpOnly',response.headers['set-cookie']);self.assertIn('Secure',response.headers['set-cookie']);self.assertIn('SameSite=lax',response.headers['set-cookie'])
        new_token=self.client.cookies.get(self.settings.cookie_name);self.assertNotEqual(new_token,token)
        with self.assertRaises(LoginError):self.store.session(token,self.settings.fingerprint,1800)
        content=self.path.read_bytes()
        for marker in (token,new_token,'CLIENT_SECRET','ACCESS_TOKEN_DO_NOT_STORE','REFRESH_TOKEN_DO_NOT_STORE'):
            self.assertNotIn(marker.encode(),content)
        self.assertNotIn('never-authority',json.dumps(first))

    def test_replay_and_other_browser_state_rejected_before_token_exchange(self):
        callback=self.begin()
        other=self.enterContext(TestClient(self.app,base_url=self.settings.public_url,follow_redirects=False))
        denied=other.get(callback);self.assertIn('loginError=login_state_invalid',denied.headers['location'])
        self.assertFalse(any(url.endswith('/token') for url,_,_ in self.provider.calls))
        self.client.get(callback)
        self.assertTrue(self.client.get('/api/session').json()['authenticated'])
        repeated=self.client.get(callback);self.assertIn('loginError=login_state_invalid',repeated.headers['location'])
        self.assertEqual(sum(url.endswith('/token') for url,_,_ in self.provider.calls),1)

    def test_signed_bad_claims_and_unknown_subject_never_authenticate(self):
        for changed in ({'iss':'https://attacker.test'},{'aud':'other-client'},{'exp':int(time.time())-120},{'nonce':'wrong'},{'aud':['client','other'],'azp':'other'},{'iat':int(time.time())+120}):
            with self.subTest(changed=changed):
                self.provider.override=changed
                response=self.client.get(self.begin());self.assertIn('loginError=id_token_invalid',response.headers['location'])
                self.assertFalse(self.client.get('/api/session').json()['authenticated'])
        self.provider.override={}
        response=self.client.get(self.begin(subject='unregistered'))
        self.assertIn('identity_not_registered',response.headers['location'])
        self.assertFalse(self.client.get('/api/session').json()['authenticated'])

    def test_csrf_logout_and_workspace_selection(self):
        info=self.login()
        body={'name':'new','base_url':'https://example.test'}
        self.assertEqual(self.client.put('/api/projects/new.json',json=body).status_code,403)
        self.assertEqual(self.client.put('/api/projects/new.json',json=body,headers={'Origin':'https://attacker.test','X-CSRF-Token':info['csrfToken']}).status_code,403)
        self.assertEqual(self.client.put('/api/projects/new.json',json=body,headers=self.headers(info)).status_code,200)
        self.assertEqual(self.client.get('/api/projects/same.json',headers={'X-Studio-Workspace':'team-b'}).status_code,403)
        switched=self.client.post('/api/session/workspace',json={'workspaceId':'team-b'},headers=self.headers(info))
        self.assertEqual(switched.status_code,200,switched.text)
        self.assertEqual(self.client.get('/api/projects/same.json').json()['name'],'team-b')
        self.assertEqual(self.client.post('/api/session/workspace',json={'workspaceId':'other'},headers=self.headers(info)).status_code,403)
        self.assertEqual(self.client.post('/api/session/logout',json={},headers=self.headers(info)).status_code,200)
        self.assertEqual(self.client.get('/api/projects').status_code,401)

    def test_email_and_role_claims_never_change_identity_or_privilege(self):
        info=self.login('bob-subject')
        self.assertEqual(info['userId'],'bob');self.assertEqual(info['workspace']['role'],'viewer')
        self.assertEqual(self.client.put('/api/projects/spoof.json',json={'name':'x','base_url':'https://example.test'},headers=self.headers(info)).status_code,403)
        self.provider.override={'email':'changed@example.test','roles':['admin']}
        again=self.login('bob-subject');self.assertEqual(again['userId'],'bob');self.assertEqual(again['workspace']['role'],'viewer')

    def test_membership_changes_audited_and_last_owner_retained(self):
        info=self.login();headers=self.headers(info)
        response=self.client.post('/api/workspace/members',headers=headers,json={'userId':'bob','role':'runner','status':'active','reason':'approved runner','revision':1})
        self.assertEqual(response.status_code,200,response.text)
        denied=self.client.post('/api/workspace/members',headers=headers,json={'userId':'alice','role':'viewer','status':'active','reason':'remove last owner','revision':1})
        self.assertEqual(denied.status_code,409)
        audit=self.client.get('/api/workspace/audit').json()['items']
        self.assertTrue(any(item['action']=='membership.changed' and item['actor_id']=='alice' and item['target']=='bob' for item in audit))

    def test_concurrent_membership_edit_has_one_winner_and_one_audit_event(self):
        from concurrent.futures import ThreadPoolExecutor
        context=RequestContext('team-a','alice','request-fixture')
        def change(role):
            try:self.store.change_member(context,'bob',role,'active','concurrent edit',1);return 200
            except LoginError as error:return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(change,['runner','editor']))
        self.assertCountEqual(outcomes,[200,409])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT version FROM memberships WHERE workspace_id='team-a' AND user_id='bob'").fetchone()[0],2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM security_events WHERE action='membership.changed'").fetchone()[0],1)

    def test_secret_access_is_audited_without_values(self):
        from api_test.project_variables import encrypt_secret
        info=self.login()
        documents=CollaborationStore(self.path,{'projects':self.root/'projects','cases':self.root/'cases','pipelines':self.root/'pipelines'},context=RequestContext('team-a','alice'))
        original=documents.get('projects','same.json')
        documents.save('projects','same.json',{**original.document,'variables':{'secret':{'TOKEN':encrypt_secret('MANAGED_SECRET_SENTINEL')}}},expected_revision=original.revision)
        with patch('api_test.ownership.OwnershipStore.authorize'),patch.object(studio,'execute_http_call',return_value=(200,{},'{"ok":true}',1)):
            response=self.client.post('/api/request',headers=self.headers(info),json={'project':'same.json','url':'/echo','headers':{'X-Token':'{{project.TOKEN}}'}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.headers.get('X-Request-ID'))
        events=self.client.get('/api/workspace/audit').json()['items']
        records=[event for event in events if event['action']=='secret.read_requested']
        self.assertEqual(len(records),1);self.assertEqual(records[0]['actor_id'],'alice')
        self.assertNotIn('MANAGED_SECRET_SENTINEL',json.dumps(events))
        self.assertNotIn(b'MANAGED_SECRET_SENTINEL',self.path.read_bytes())

    def test_broken_signature_algorithm_at_hash_and_future_claims(self):
        callback=self.begin()
        real=self.provider.key
        try:
            self.provider.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
            response=self.client.get(callback);self.assertIn('id_token_invalid',response.headers['location'])
        finally:self.provider.key=real
        for override in ({'at_hash':'invalid'},{'aud':['client','other']},{'exp':float('inf')}):
            self.provider.override=override
            response=self.client.get(self.begin());self.assertIn('id_token_invalid',response.headers['location'])
        self.provider.override={}
        original=self.provider.json
        def unsigned(url,**options):
            value=original(url,**options)
            if url.endswith('/token'):
                claims=jwt.decode(value['id_token'],options={'verify_signature':False})
                value['id_token']=jwt.encode(claims,key='',algorithm='none')
            return value
        with patch.object(self.provider,'json',side_effect=unsigned):
            response=self.client.get(self.begin());self.assertIn('id_token_invalid',response.headers['location'])

    def test_session_key_change_and_reprovision_cannot_reassign_identity(self):
        self.login()
        with self.assertRaises(LoginError):self.store.session(self.client.cookies.get(self.settings.cookie_name),'changed-config',1800)
        with self.assertRaises(LoginError):self.store.provision(issuer=self.settings.issuer,subject='alice-subject',user_id='attacker',display_name='Attacker',workspace_id='team-a',workspace_name='A',role='owner')
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT user_id FROM user_identities WHERE provider_subject=?',('alice-subject',)).fetchone()[0],'alice')

    def test_expiry_revocation_and_switch_from_revoked_workspace(self):
        info=self.login()
        with closing(connect(self.path)) as db,db:db.execute("UPDATE memberships SET status='disabled' WHERE user_id='alice' AND workspace_id='team-a'")
        self.assertEqual(self.client.get('/api/projects').status_code,403)
        available=self.client.get('/api/session').json();self.assertIsNone(available['workspace']);self.assertEqual(len(available['workspaces']),1)
        self.assertEqual(self.client.post('/api/session/workspace',headers=self.headers(info),json={'workspaceId':'team-b'}).status_code,200)
        with closing(connect(self.path)) as db,db:db.execute('UPDATE login_sessions SET idle_expires_at=?',(time.time()-1,))
        self.assertEqual(self.client.get('/api/projects').status_code,401)

if __name__=='__main__':unittest.main()
