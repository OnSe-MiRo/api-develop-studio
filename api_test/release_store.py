"""Immutable API release snapshots and transactional lifecycle approvals."""
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import base64
from api_test.portal_document import portal_metadata
import json
from pathlib import Path
import re
import threading
import uuid

from api_test.database import connect, initialize_local_context, require_membership
from api_test.migrations import Migration, MigrationRunner, migrate_studio_database
from api_test.contracts import compare, lint, project_document, ContractError
from api_test.contracts.validation import operations

MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_WORKSPACE_ARTIFACT_BYTES = 128 * 1024 * 1024
SDK_LANGUAGES = ('python','javascript','typescript','java','kotlin','go','csharp')
VERSION = re.compile(r'^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$')


class ReleaseError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status_code = status


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def source_hash(source):
    return hashlib.sha256(canonical(source).encode()).hexdigest()


def _schema(db):
    db.execute('''CREATE TABLE api_releases (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
        project_id TEXT NOT NULL REFERENCES documents(id), project_reference TEXT NOT NULL,
        version TEXT NOT NULL, source_revision INTEGER NOT NULL, source_digest TEXT NOT NULL,
        source_json TEXT NOT NULL, document_json TEXT NOT NULL, notes TEXT NOT NULL,
        baseline_id TEXT REFERENCES api_releases(id) DEFERRABLE INITIALLY DEFERRED, comparison_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('draft','published','deprecated','retired')),
        revision INTEGER NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, published_at TEXT,
        UNIQUE(workspace_id,project_id,version),
        FOREIGN KEY(project_id,source_revision) REFERENCES document_revisions(document_id,revision))''')
    db.execute('''CREATE TABLE api_release_events (
        id TEXT PRIMARY KEY, release_id TEXT NOT NULL REFERENCES api_releases(id),
        workspace_id TEXT NOT NULL REFERENCES workspaces(id), revision INTEGER NOT NULL,
        from_state TEXT, to_state TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id),
        reason TEXT NOT NULL, acknowledge_changes INTEGER NOT NULL, created_at TEXT NOT NULL,
        request_id TEXT, UNIQUE(release_id,revision))''')
    db.execute('CREATE INDEX api_releases_project ON api_releases(workspace_id,project_reference,created_at DESC,id DESC)')
    db.execute('CREATE INDEX api_release_events_scope ON api_release_events(workspace_id,release_id,revision)')


def _portal_schema(db):
    db.execute("ALTER TABLE api_releases ADD COLUMN portal_json TEXT NOT NULL DEFAULT '{}'")
    # Backfill from immutable project revisions, never current environment settings.
    for release in db.execute('SELECT id,project_id,source_revision FROM api_releases').fetchall():
        row=db.execute('SELECT content FROM document_revisions WHERE document_id=? AND revision=?',(release[1],release[2])).fetchone()
        db.execute('UPDATE api_releases SET portal_json=? WHERE id=?',(canonical(portal_metadata(json.loads(row[0]))),release[0]))
    db.execute("""CREATE TABLE api_release_artifacts (
        id TEXT PRIMARY KEY, release_id TEXT NOT NULL REFERENCES api_releases(id),
        workspace_id TEXT NOT NULL REFERENCES workspaces(id), language TEXT NOT NULL,
        source_digest TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
        filename TEXT NOT NULL, generator_version TEXT NOT NULL, payload_base64 TEXT,
        created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
        purged_by TEXT REFERENCES users(id), purged_at TEXT, purge_reason TEXT,
        UNIQUE(release_id,language))""")
    db.execute('CREATE INDEX api_release_artifact_scope ON api_release_artifacts(workspace_id,release_id)')


def migrate_release_database(db):
    return MigrationRunner((Migration(1,'immutable API releases and approval events',_schema),
        Migration(2,'private release portal and durable SDK artifacts',_portal_schema))).run(db,'release_schema_migrations')


def migrate_studio_with_releases(db):
    migrate_studio_database(db)
    migrate_release_database(db)


class ReleaseStore:
    def __init__(self, path, *, context):
        self.path, self.context = Path(path), context
        self._lock = threading.Lock()
        self._initialized = False

    def initialize(self):
        with self._lock:
            if not self._initialized:
                with closing(connect(self.path)) as db:
                    migrate_studio_with_releases(db)
                    with db: initialize_local_context(db)
                self._initialized = True

    @contextmanager
    def connection(self, *, roles=None):
        self.initialize()
        db = connect(self.path)
        try:
            role = require_membership(db,self.context)
            if roles is not None and role not in roles:
                raise ReleaseError('이 릴리스 작업을 수행할 권한이 없습니다.',403)
            db.commit()
            yield db
        finally:
            db.close()

    def _project(self, db, reference, *, lock=False):
        suffix = ' FOR UPDATE' if lock and getattr(db,'dialect','')=='postgresql' else ''
        row = db.execute("SELECT id,current_revision FROM documents WHERE workspace_id=? AND kind='projects' AND reference=? AND deleted_at IS NULL" + suffix,
                         (self.context.workspace_id,reference)).fetchone()
        if row is None: raise ReleaseError('프로젝트를 찾을 수 없습니다.',404)
        return row

    def _row(self, db, reference, release_id):
        project=self._project(db,reference)
        row=db.execute('SELECT * FROM api_releases WHERE workspace_id=? AND project_id=? AND id=?',
                       (self.context.workspace_id,project['id'],release_id)).fetchone()
        if row is None: raise ReleaseError('릴리스를 찾을 수 없습니다.',404)
        return row

    @staticmethod
    def _view(row, *, full=False):
        result={key:row[field] for key,field in {'id':'id','project':'project_reference','version':'version','projectRevision':'source_revision','sourceDigest':'source_digest','baselineId':'baseline_id','state':'state','revision':'revision','createdBy':'created_by','createdAt':'created_at','updatedAt':'updated_at','publishedAt':'published_at'}.items()}
        if full:
            document=json.loads(row['document_json'])
            result.update(notes=row['notes'],comparison=json.loads(row['comparison_json']),deprecatedOperations=[{'method':method.upper(),'path':path,'operationId':operation.get('operationId','')} for path,method,operation,_ in operations(document) if operation.get('deprecated') is True])
        return result

    def list(self, reference, *, limit=20, before=None, published_only=False):
        if type(limit) is not int or not 1<=limit<=100: raise ReleaseError('limit은 1~100이어야 합니다.')
        with self.connection() as db:
            project=self._project(db,reference)
            query='SELECT id,project_reference,version,source_revision,source_digest,baseline_id,state,revision,created_by,created_at,updated_at,published_at FROM api_releases WHERE workspace_id=? AND project_id=?'
            params=[self.context.workspace_id,project['id']]
            if published_only: query+=" AND state IN ('published','deprecated')"
            if before:
                cursor=self._row(db,reference,before)
                query+=' AND (created_at < ? OR (created_at = ? AND id < ?))'
                params += [cursor['created_at'],cursor['created_at'],cursor['id']]
            rows=db.execute(query+' ORDER BY created_at DESC,id DESC LIMIT ?',[*params,limit+1]).fetchall()
        return {'items':[self._view(row) for row in rows[:limit]],'nextCursor':rows[limit-1]['id'] if len(rows)>limit else None}

    def detail(self, reference, release_id):
        with self.connection() as db:
            row=self._row(db,reference,release_id)
            events=db.execute('SELECT revision,from_state,to_state,actor_id,reason,acknowledge_changes,created_at,request_id FROM api_release_events WHERE workspace_id=? AND release_id=? ORDER BY revision', (self.context.workspace_id,release_id)).fetchall()
        return {**self._view(row,full=True),'events':[dict(item) for item in events]}

    def source(self, reference, release_id):
        with self.connection() as db: row=self._row(db,reference,release_id)
        return {'releaseId':row['id'],'projectRevision':row['source_revision'],'sourceDigest':row['source_digest'],'source':json.loads(row['source_json'])}

    def create(self, reference, body):
        version,revision,notes=body.get('version'),body.get('projectRevision'),body.get('notes','')
        if not isinstance(version,str) or len(version)>80 or not VERSION.fullmatch(version): raise ReleaseError('version은 1.2.3 형식이어야 합니다.')
        if type(revision) is not int or revision<1: raise ReleaseError('프로젝트 revision이 필요합니다.',409)
        if not isinstance(notes,str) or len(notes)>20000: raise ReleaseError('변경 설명은 20,000자 이하여야 합니다.')
        baseline=body.get('baselineId') or None
        if baseline is not None and not isinstance(baseline,str): raise ReleaseError('기준 릴리스를 확인하세요.')
        with self.connection(roles={'owner','admin','editor'}) as db,db:
            db.execute('BEGIN IMMEDIATE')
            project=self._project(db,reference,lock=True)
            if project['current_revision']!=revision: raise ReleaseError('프로젝트 revision이 변경됐습니다. 새로고침하세요.',409)
            if db.execute('SELECT 1 FROM api_releases WHERE workspace_id=? AND project_id=? AND version=?',(self.context.workspace_id,project['id'],version)).fetchone(): raise ReleaseError('이미 사용한 릴리스 version입니다.',409)
            stored=db.execute('SELECT content FROM document_revisions WHERE document_id=? AND revision=?',(project['id'],revision)).fetchone()
            project_document_raw=json.loads(stored['content'])
            try:
                document=project_document(project_document_raw)
                source=({'kind':'bundle',**deepcopy(project_document_raw['docs_bundle'])} if project_document_raw.get('docs_bundle') is not None else {'kind':'file','document':deepcopy(project_document_raw['docs_file']['document'])})
                # Keep only canonical bundle fields, not arbitrary project metadata.
                if source['kind']=='bundle': source={key:source[key] for key in ('kind','entrypoint','files')}
                if source['kind']=='bundle':
                    for filename in source['files']:
                        if not isinstance(filename,str) or any(part in ('','.', '..') or ':' in part or chr(92) in part for part in filename.split('/')):
                            raise ReleaseError('Bundle 파일 이름은 안전한 상대 경로여야 합니다.')
                encoded_source=canonical(source)
                if len(encoded_source.encode())>MAX_SOURCE_BYTES: raise ReleaseError('명세 원본은 5 MiB 이하여야 합니다.')
                issues=lint(document)
                if any(item['severity']=='error' for item in issues): raise ReleaseError('OpenAPI lint 오류를 먼저 해결하세요.')
                if baseline is None:
                    latest=db.execute("SELECT id FROM api_releases WHERE workspace_id=? AND project_id=? AND state IN ('published','deprecated') ORDER BY published_at DESC,id DESC LIMIT 1",(self.context.workspace_id,project['id'])).fetchone()
                    baseline=latest['id'] if latest else None
                if baseline:
                    previous=self._row(db,reference,baseline)
                    if previous['state'] not in ('published','deprecated'): raise ReleaseError('발행된 기준 릴리스를 선택하세요.')
                    baseline_document=json.loads(previous['document_json'])
                    comparison=compare(baseline_document,document)
                else:
                    baseline_document={'paths':{}}
                    comparison={'baselineHash':None,'currentHash':source_hash(document),'issues':issues,'changes':[],'compatible':True}
                old_operations={(path,method):operation for path,method,operation,_ in operations(baseline_document)}
                new_operations={(path,method):operation for path,method,operation,_ in operations(document)}
                changes=[]
                for key in sorted(set(old_operations)|set(new_operations)):
                    old,new=old_operations.get(key),new_operations.get(key)
                    kind='added' if old is None else 'removed' if new is None else 'deprecated' if not old.get('deprecated') and new.get('deprecated') else 'restored' if old.get('deprecated') and not new.get('deprecated') else 'changed' if canonical(old)!=canonical(new) else None
                    if kind: changes.append({'kind':kind,'path':key[0],'method':key[1].upper()})
                comparison['operationChanges']=changes
            except (ContractError,KeyError,TypeError,RecursionError,ValueError) as exc:
                if isinstance(exc,ReleaseError): raise
                raise ReleaseError('저장된 OpenAPI 파일 또는 bundle을 확인하세요. URL만 있는 revision은 고정할 수 없습니다.') from exc
            release_id=str(uuid.uuid4());stamp=datetime.now(timezone.utc).isoformat()
            db.execute('''INSERT INTO api_releases(id,workspace_id,project_id,project_reference,version,source_revision,source_digest,source_json,document_json,notes,baseline_id,comparison_json,state,revision,created_by,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'draft',1,?,?,?)''', (release_id,self.context.workspace_id,project['id'],reference,version,revision,source_hash(source),encoded_source,canonical(document),notes,baseline,canonical(comparison),self.context.user_id,stamp,stamp))
            db.execute('UPDATE api_releases SET portal_json=? WHERE id=?',(canonical(portal_metadata(project_document_raw)),release_id))
            self._event(db,release_id,1,None,'draft','릴리스 초안 생성',False,stamp)
        return self.detail(reference,release_id)

    def _event(self, db, release_id, revision, before, after, reason, acknowledge, stamp):
        db.execute('''INSERT INTO api_release_events(id,release_id,workspace_id,revision,from_state,to_state,actor_id,reason,acknowledge_changes,created_at,request_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (str(uuid.uuid4()),release_id,self.context.workspace_id,revision,before,after,self.context.user_id,reason,int(acknowledge),stamp,self.context.request_id))

    def transition(self, reference, release_id, body):
        state,revision,reason=body.get('state'),body.get('revision'),body.get('reason')
        acknowledge=body.get('acknowledgeChanges') is True
        if not isinstance(state,str): raise ReleaseError('상태 값을 확인하세요.')
        if type(revision) is not int or revision<1: raise ReleaseError('릴리스 revision을 확인하세요.',409)
        if not isinstance(reason,str) or not reason.strip() or len(reason)>2000: raise ReleaseError('전환 사유를 1~2,000자로 입력하세요.')
        allowed={'draft':{'published','retired'},'published':{'deprecated','retired'},'deprecated':{'retired'},'retired':set()}
        with self.connection(roles={'owner','admin'}) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=self._row(db,reference,release_id)
            if row['revision']!=revision: raise ReleaseError('릴리스가 변경됐습니다. 다시 조회하세요.',409)
            if state not in allowed[row['state']]: raise ReleaseError('허용되지 않는 릴리스 상태 전환입니다.',409)
            comparison=json.loads(row['comparison_json'])
            if state=='published':
                if any(item['severity']=='error' for item in comparison['issues']): raise ReleaseError('호환성 분석 오류가 있어 발행할 수 없습니다.',409)
                if comparison['changes'] and not acknowledge: raise ReleaseError('호환성 변경을 확인하고 명시적으로 승인하세요.',409)
            stamp=datetime.now(timezone.utc).isoformat()
            updated=db.execute('UPDATE api_releases SET state=?,revision=revision+1,updated_at=?,published_at=? WHERE id=? AND workspace_id=? AND revision=?', (state,stamp,stamp if state=='published' else row['published_at'],release_id,self.context.workspace_id,revision))
            if updated.rowcount!=1: raise ReleaseError('릴리스가 동시에 변경됐습니다.',409)
            self._event(db,release_id,revision+1,row['state'],state,reason.strip(),acknowledge,stamp)
        return self.detail(reference,release_id)


    @staticmethod
    def _artifact_view(row):
        return {key:row[field] for key,field in {'id':'id','language':'language','sourceDigest':'source_digest','sha256':'sha256','sizeBytes':'size_bytes','filename':'filename','generatorVersion':'generator_version','createdBy':'created_by','createdAt':'created_at','purgedAt':'purged_at'}.items()}

    @staticmethod
    def _visible(row):
        if row['state'] not in ('published','deprecated'):
            raise ReleaseError('발행된 릴리스를 찾을 수 없습니다.',404)

    def portal(self, reference, release_id):
        with self.connection() as db:
            row=self._row(db,reference,release_id);self._visible(row)
            role=require_membership(db,self.context)
            artifacts=db.execute('SELECT id,language,source_digest,sha256,size_bytes,filename,generator_version,created_by,created_at,purged_at FROM api_release_artifacts WHERE workspace_id=? AND release_id=? ORDER BY language',(self.context.workspace_id,release_id)).fetchall()
        return {'release':self._view(row,full=True),'document':json.loads(row['document_json']),
                'environments':json.loads(row['portal_json']).get('servers',[]),
                'artifacts':[self._artifact_view(item) for item in artifacts],
                'permissions':{'generateSdk':role in ('owner','admin','editor','runner')}}

    def sdk_snapshot(self, reference, release_id, language):
        from api_test.sdk_generation import initial_metadata
        if language not in SDK_LANGUAGES:
            raise ReleaseError('지원하지 않는 SDK 언어입니다.')
        with self.connection(roles={'owner','admin','editor','runner'}) as db:
            row=self._row(db,reference,release_id);self._visible(row)
            if db.execute('SELECT 1 FROM api_release_artifacts WHERE release_id=? AND language=?',(release_id,language)).fetchone():
                raise ReleaseError('해당 언어의 SDK가 이미 보존돼 있습니다.',409)
        name=re.sub(r'[^A-Za-z0-9_-]+','-',reference.removesuffix('.json')+'-'+row['version']).strip('-')[:100]
        snapshot={'project':reference,'projectName':name,'projectRevision':row['source_revision'],'language':language,
                  'source':json.loads(row['source_json']),'sourceDigest':row['source_digest']}
        return snapshot,{'releaseId':release_id,'version':row['version'],**initial_metadata(snapshot)}

    def keep_artifact(self, reference, release_id, language, payload, filename, digest, generator_version):
        if language not in SDK_LANGUAGES:raise ReleaseError("지원하지 않는 SDK 언어입니다.")
        if not isinstance(payload,bytes) or not 0<len(payload)<=MAX_ARTIFACT_BYTES:
            raise ReleaseError('SDK ZIP은 32 MiB 이하여야 합니다.')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.zip',filename):raise ReleaseError('SDK 파일 이름을 확인하세요.')
        encoded=base64.b64encode(payload).decode('ascii')
        with self.connection(roles={'owner','admin','editor','runner'}) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=self._row(db,reference,release_id);self._visible(row)
            if row['source_digest']!=digest:raise ReleaseError('SDK 원본 지문이 릴리스와 다릅니다.',409)
            if db.execute('SELECT 1 FROM api_release_artifacts WHERE release_id=? AND language=?',(release_id,language)).fetchone():
                raise ReleaseError('해당 언어의 SDK가 다른 작업에서 이미 보존됐습니다.',409)
            total=db.execute('SELECT COALESCE(SUM(size_bytes),0) AS total FROM api_release_artifacts WHERE workspace_id=? AND purged_at IS NULL',(self.context.workspace_id,)).fetchone()['total']
            if total+len(payload)>MAX_WORKSPACE_ARTIFACT_BYTES:raise ReleaseError('Workspace SDK 보존 한도128 MiB를 초과했습니다. 폐기 릴리스의 SDK를 정리하세요.',429)
            artifact_id=str(uuid.uuid4());stamp=datetime.now(timezone.utc).isoformat()
            db.execute("""INSERT INTO api_release_artifacts(id,release_id,workspace_id,language,source_digest,sha256,size_bytes,filename,generator_version,payload_base64,created_by,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(artifact_id,release_id,self.context.workspace_id,language,digest,hashlib.sha256(payload).hexdigest(),len(payload),filename,generator_version,encoded,self.context.user_id,stamp))
            artifact=db.execute('SELECT * FROM api_release_artifacts WHERE id=?',(artifact_id,)).fetchone()
        return self._artifact_view(artifact)

    def download_artifact(self, reference, release_id, language):
        with self.connection() as db:
            row=self._row(db,reference,release_id);self._visible(row)
            artifact=db.execute('SELECT * FROM api_release_artifacts WHERE workspace_id=? AND release_id=? AND language=? AND purged_at IS NULL',(self.context.workspace_id,release_id,language)).fetchone()
            if artifact is None:raise ReleaseError('SDK 파일을 찾을 수 없습니다.',404)
        try: payload=base64.b64decode(artifact['payload_base64'],validate=True)
        except (ValueError,TypeError) as exc: raise ReleaseError('SDK 파일 무결성을 확인하지 못했습니다.',503) from exc
        if artifact['source_digest']!=row['source_digest']:raise ReleaseError('SDK 원본 지문이 릴리스와 다릅니다.',503)
        if len(payload)!=artifact['size_bytes'] or hashlib.sha256(payload).hexdigest()!=artifact['sha256']:
            raise ReleaseError('SDK 파일 무결성을 확인하지 못했습니다.',503)
        return payload,artifact['filename'],artifact['sha256']

    def purge_artifact(self, reference, release_id, language, reason):
        if not isinstance(reason,str) or not reason.strip() or len(reason)>2000:raise ReleaseError('정리 사유가 필요합니다.')
        with self.connection(roles={'owner','admin'}) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT r.state,d.deleted_at FROM api_releases r JOIN documents d ON d.id=r.project_id WHERE r.workspace_id=? AND r.project_reference=? AND r.id=?',(self.context.workspace_id,reference,release_id)).fetchone()
            if row is None:raise ReleaseError('릴리스를 찾을 수 없습니다.',404)
            if row['state']!='retired' and row['deleted_at'] is None:raise ReleaseError('폐기된 릴리스 또는 삭제된 프로젝트의 SDK만 정리할 수 있습니다.',409)
            changed=db.execute('UPDATE api_release_artifacts SET payload_base64=NULL,purged_by=?,purged_at=?,purge_reason=? WHERE workspace_id=? AND release_id=? AND language=? AND purged_at IS NULL',(self.context.user_id,datetime.now(timezone.utc).isoformat(),reason.strip(),self.context.workspace_id,release_id,language))
            if changed.rowcount!=1:raise ReleaseError('정리할 SDK 파일이 없습니다.',404)
        return {'purged':True}
