"""Server-side OIDC transactions, opaque sessions and workspace security audit."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
import threading
import time
import uuid

from api_test.database import connect, initialize_local_context, RequestContext, require_membership
from api_test.migrations import Migration, MigrationRunner, migrate_studio_database
from api_test.oidc_client import LoginError

TOKEN = re.compile(r'^[A-Za-z0-9_-]{43}$')
ROLES = {'owner','admin','editor','runner','viewer'}


def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()


def _schema(db):
    db.execute('''CREATE TABLE oidc_login_states (
        state_hash TEXT PRIMARY KEY,binding_hash TEXT NOT NULL,config_hash TEXT NOT NULL,
        encrypted_payload TEXT NOT NULL,expires_at REAL NOT NULL,created_at REAL NOT NULL)''')
    db.execute('CREATE INDEX oidc_state_expiry ON oidc_login_states(expires_at)')
    db.execute('''CREATE TABLE login_sessions (
        session_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
        workspace_id TEXT NOT NULL REFERENCES workspaces(id),config_hash TEXT NOT NULL,
        created_at REAL NOT NULL,idle_expires_at REAL NOT NULL,expires_at REAL NOT NULL)''')
    db.execute('CREATE INDEX login_session_user ON login_sessions(user_id,created_at)')
    db.execute('''CREATE TABLE security_events (
        id TEXT PRIMARY KEY,workspace_id TEXT REFERENCES workspaces(id),actor_id TEXT REFERENCES users(id),
        action TEXT NOT NULL,target TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL,request_id TEXT)''')
    db.execute('CREATE INDEX security_events_scope ON security_events(workspace_id,created_at DESC,id DESC)')


def _membership_versions(db):
    db.execute('ALTER TABLE memberships ADD COLUMN version INTEGER NOT NULL DEFAULT 1')


def migrate_identity_database(db):
    return MigrationRunner((Migration(1,'OIDC sessions and security audit',_schema), Migration(2,'membership optimistic revision guards',_membership_versions))).run(db,'identity_schema_migrations')


def migrate_studio_with_identity(db):
    migrate_studio_database(db);migrate_identity_database(db)


class IdentityStore:
    def __init__(self,path):self.path=path;self._lock=threading.Lock();self._initialized=False
    def initialize(self):
        with self._lock:
            if self._initialized:return
            with closing(connect(self.path)) as db:
                migrate_studio_with_identity(db)
                with db:initialize_local_context(db)
            self._initialized=True

    @contextmanager
    def connection(self):
        self.initialize()
        db=connect(self.path)
        try:yield db
        finally:db.close()

    @staticmethod
    def _audit(db,workspace,user,action,target='',detail=None,request_id=None):
        db.execute('INSERT INTO security_events(id,workspace_id,actor_id,action,target,detail,created_at,request_id) VALUES(?,?,?,?,?,?,?,?)',
            (str(uuid.uuid4()),workspace,user,action,target,json.dumps(detail or {},sort_keys=True),stamp(),request_id or uuid.uuid4().hex))

    def audit(self,context,action,target='',detail=None):
        with self.connection() as db,db:
            if context is not None:require_membership(db,context)
            self._audit(db,context.workspace_id if context else None,context.user_id if context else None,action,target,detail,context.request_id if context else None)

    @staticmethod
    def _prune(db,config_hash):
        now=time.time()
        db.execute('DELETE FROM oidc_login_states WHERE expires_at<=? OR config_hash<>?',(now,config_hash))
        db.execute('DELETE FROM login_sessions WHERE expires_at<=? OR idle_expires_at<=? OR config_hash<>?',(now,now,config_hash))

    def save_state(self,state,binding,config,payload):
        with self.connection() as db,db:
            db.execute('BEGIN IMMEDIATE');self._prune(db,config)
            count=db.execute('SELECT COUNT(*) FROM oidc_login_states').fetchone()[0]
            browser=db.execute('SELECT COUNT(*) FROM oidc_login_states WHERE binding_hash=?',(digest(binding),)).fetchone()[0]
            if count>=1000 or browser>=5:raise LoginError('login_capacity_exceeded',429)
            now=time.time()
            db.execute('INSERT INTO oidc_login_states VALUES(?,?,?,?,?,?)',(digest(state),digest(binding),config,payload,now+600,now))

    def consume_state(self,state,binding,config):
        if not isinstance(state,str) or not TOKEN.fullmatch(state) or not isinstance(binding,str) or not TOKEN.fullmatch(binding):raise LoginError('login_state_invalid',401)
        with self.connection() as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT encrypted_payload,binding_hash FROM oidc_login_states WHERE state_hash=? AND config_hash=? AND expires_at>?',(digest(state),config,time.time())).fetchone()
            if row is None or not secrets.compare_digest(row['binding_hash'],digest(binding)):raise LoginError('login_state_invalid',401)
            db.execute('DELETE FROM oidc_login_states WHERE state_hash=?',(digest(state),))
        return row['encrypted_payload']

    @staticmethod
    def _memberships(db,user):
        return [dict(row) for row in db.execute("SELECT w.id,w.name,m.role FROM memberships m JOIN workspaces w ON w.id=m.workspace_id JOIN users u ON u.id=m.user_id WHERE m.user_id=? AND m.status='active' AND u.status='active' AND w.status='active' ORDER BY w.name,w.id",(user,)).fetchall()]

    def start_session(self,issuer,subject,config,idle_seconds,max_seconds,old_session=None):
        token=secrets.token_urlsafe(32)
        with self.connection() as db,db:
            db.execute('BEGIN IMMEDIATE');self._prune(db,config)
            row=db.execute("SELECT u.id FROM user_identities i JOIN users u ON u.id=i.user_id WHERE i.provider=? AND i.provider_subject=? AND u.status='active'",(issuer,subject)).fetchone()
            if row is None:raise LoginError('identity_not_registered',403)
            user=row['id'];memberships=self._memberships(db,user)
            if not memberships:raise LoginError('workspace_membership_required',403)
            workspace=memberships[0]['id']
            if old_session and TOKEN.fullmatch(old_session):
                old=db.execute('SELECT workspace_id,user_id FROM login_sessions WHERE session_hash=?',(digest(old_session),)).fetchone()
                if old and old['user_id']==user and old['workspace_id'] in {item['id'] for item in memberships}:workspace=old['workspace_id']
                db.execute('DELETE FROM login_sessions WHERE session_hash=?',(digest(old_session),))
            sessions=db.execute('SELECT session_hash FROM login_sessions WHERE user_id=? ORDER BY created_at DESC',(user,)).fetchall()
            for stale in sessions[9:]:db.execute('DELETE FROM login_sessions WHERE session_hash=?',(stale['session_hash'],))
            now=time.time()
            db.execute('INSERT INTO login_sessions VALUES(?,?,?,?,?,?,?)',(digest(token),user,workspace,config,now,now+idle_seconds,now+max_seconds))
            self._audit(db,workspace,user,'login.success',detail={'issuer':issuer})
        return token

    def session(self,token,config,idle_seconds,*,require_workspace=True):
        if not isinstance(token,str) or not TOKEN.fullmatch(token):raise LoginError('session_required',401)
        now=time.time()
        with self.connection() as db,db:
            row=db.execute("SELECT s.*,u.display_name FROM login_sessions s JOIN users u ON u.id=s.user_id WHERE s.session_hash=? AND s.config_hash=? AND s.expires_at>? AND s.idle_expires_at>? AND u.status='active'",(digest(token),config,now,now)).fetchone()
            if row is None:raise LoginError('session_expired',401)
            memberships=self._memberships(db,row['user_id'])
            membership=next((item for item in memberships if item['id']==row['workspace_id']),None)
            if require_workspace and membership is None:raise LoginError('workspace_membership_required',403)
            if row['idle_expires_at']<now+idle_seconds-60:
                db.execute('UPDATE login_sessions SET idle_expires_at=? WHERE session_hash=?',(min(now+idle_seconds,row['expires_at']),digest(token)))
        return {'userId':row['user_id'],'displayName':row['display_name'],'workspace':membership,'workspaces':memberships,'expiresAt':row['expires_at']}

    def logout(self,token,config,idle_seconds):
        session=self.session(token,config,idle_seconds,require_workspace=False)
        with self.connection() as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_sessions WHERE session_hash=?',(digest(token),))
            self._audit(db,session['workspace']['id'] if session['workspace'] else None,session['userId'],'logout')

    def switch_workspace(self,token,config,idle_seconds,workspace):
        session=self.session(token,config,idle_seconds,require_workspace=False)
        try:context=RequestContext(workspace,session['userId'])
        except (ValueError,TypeError) as exc:raise LoginError('invalid_workspace') from exc
        with self.connection() as db,db:
            db.execute('BEGIN IMMEDIATE')
            try:require_membership(db,context)
            except PermissionError as exc:raise LoginError('workspace_membership_required',403) from exc
            changed=db.execute('UPDATE login_sessions SET workspace_id=? WHERE session_hash=? AND config_hash=? AND expires_at>? AND idle_expires_at>?',(workspace,digest(token),config,time.time(),time.time()))
            if changed.rowcount!=1:raise LoginError('session_expired',401)
            self._audit(db,workspace,session['userId'],'workspace.selected')

    def provision(self,*,issuer,subject,user_id,display_name,workspace_id,workspace_name,role):
        """Explicit operator CLI only; never invoked by an anonymous login callback."""
        RequestContext(workspace_id,user_id)
        if role not in ROLES or not isinstance(subject,str) or not 1<=len(subject)<=512 or not display_name or not workspace_name:raise LoginError('invalid_identity_provisioning')
        with self.connection() as db,db:
            db.execute('BEGIN IMMEDIATE');now=stamp()
            mapped=db.execute('SELECT user_id FROM user_identities WHERE provider=? AND provider_subject=?',(issuer,subject)).fetchone()
            if mapped is not None and mapped['user_id']!=user_id:raise LoginError('identity_already_linked',409)
            db.execute('INSERT OR IGNORE INTO users(id,display_name,created_at,updated_at) VALUES(?,?,?,?)',(user_id,display_name,now,now))
            db.execute('INSERT OR IGNORE INTO workspaces(id,name,created_at,updated_at) VALUES(?,?,?,?)',(workspace_id,workspace_name,now,now))
            db.execute('INSERT OR IGNORE INTO user_identities(user_id,provider,provider_subject) VALUES(?,?,?)',(user_id,issuer,subject))
            existing=db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?',(workspace_id,user_id)).fetchone()
            if existing is None:db.execute('INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES(?,?,?,?)',(workspace_id,user_id,role,now))
            elif existing['role']!=role:raise LoginError('membership_exists_use_role_change',409)
            self._audit(db,workspace_id,user_id,'identity.provisioned',detail={'issuer':issuer,'role':role,'operator':'local CLI'})

    def members(self,context):
        with self.connection() as db:
            role=require_membership(db,context)
            if role not in ('owner','admin'):raise LoginError('admin_required',403)
            return [dict(row) for row in db.execute('SELECT m.user_id,u.display_name,m.role,m.status,m.version FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? ORDER BY u.display_name,u.id',(context.workspace_id,)).fetchall()]

    def change_member(self,context,user_id,role,status,reason,revision):
        if not isinstance(role,str) or role not in ROLES or not isinstance(status,str) or status not in ('active','disabled') or not isinstance(reason,str) or not 1<=len(reason.strip())<=2000:raise LoginError('invalid_membership_change')
        if type(revision) is not int or revision<1:raise LoginError('membership_revision_required',409)
        with self.connection() as db,db:
            db.execute('BEGIN IMMEDIATE')
            actor_role=require_membership(db,context)
            if actor_role not in ('owner','admin'):raise LoginError('admin_required',403)
            row=db.execute('SELECT role,status,version FROM memberships WHERE workspace_id=? AND user_id=?',(context.workspace_id,user_id)).fetchone()
            if row is None:raise LoginError('member_not_found',404)
            if row['version']!=revision:raise LoginError('membership_revision_conflict',409)
            if (row['role']=='owner' or role=='owner') and actor_role!='owner':raise LoginError('owner_required',403)
            if row['role']=='owner' and row['status']=='active' and (role!='owner' or status!='active'):
                count=db.execute("SELECT COUNT(*) FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND m.role='owner' AND m.status='active' AND u.status='active'",(context.workspace_id,)).fetchone()[0]
                if count<=1:raise LoginError('last_owner_required',409)
            db.execute('UPDATE memberships SET role=?,status=?,version=version+1 WHERE workspace_id=? AND user_id=? AND version=?',(role,status,context.workspace_id,user_id,revision))
            self._audit(db,context.workspace_id,context.user_id,'membership.changed',user_id,{'before':dict(row),'role':role,'status':status,'reason':reason.strip()},context.request_id)

    def events(self,context,*,before=None,limit=50):
        if type(limit) is not int or not 1<=limit<=100:raise LoginError('invalid_limit')
        with self.connection() as db:
            if require_membership(db,context) not in ('owner','admin'):raise LoginError('admin_required',403)
            where='workspace_id=?';params=[context.workspace_id]
            if before:
                cursor=db.execute('SELECT id,created_at FROM security_events WHERE workspace_id=? AND id=?',(context.workspace_id,before)).fetchone()
                if cursor is None:raise LoginError('audit_cursor_not_found',404)
                where+=' AND (created_at<? OR (created_at=? AND id<?))';params += [cursor['created_at'],cursor['created_at'],cursor['id']]
            rows=db.execute('SELECT * FROM security_events WHERE '+where+' ORDER BY created_at DESC,id DESC LIMIT ?',[*params,limit+1]).fetchall()
        return {'items':[{**dict(row),'detail':json.loads(row['detail'])} for row in rows[:limit]],'nextCursor':rows[limit-1]['id'] if len(rows)>limit else None}
