"""Private release documentation and bounded, release-pinned SDK jobs."""
import io
import json
import threading
import zipfile
import yaml
from importlib.metadata import version

from starlette.responses import Response
from api_test.release_store import ReleaseError, source_hash
from api_test.sdk_generation import execute_snapshot
from api_test.services.releases import _call

DOWNLOAD_SLOTS = threading.BoundedSemaphore(4)


class ArtifactResponse(Response):
    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope,receive,send)
        finally:
            DOWNLOAD_SLOTS.release()


def list_portal_releases(request, studio):
    def operation(store,reference):
        try:limit=int(request.query_value('limit') or '20')
        except ValueError as exc:raise studio.ApiError('limit을 확인하세요.') from exc
        return request.json_response(200,store.list(reference,limit=limit,before=request.query_value('before'),published_only=True))
    return _call(request,studio,operation)


def get_portal(request, studio):
    return _call(request,studio,lambda store,reference:request.json_response(200,store.portal(reference,request.request.path_params['releaseId'])))


def _manifest_zip(payload, metadata, language, generator, snapshot):
    output=io.BytesIO(payload)
    with zipfile.ZipFile(output,'a',zipfile.ZIP_DEFLATED) as archive:
        roots={name.split('/')[0] for name in archive.namelist()}
        if len(roots)!=1:raise ReleaseError('SDK archive 구조를 확인하지 못했습니다.')
        root=next(iter(roots))
        source=snapshot['source']
        source_path='openapi.yaml' if source['kind']=='file' else 'openapi/'+source['entrypoint']
        if source['kind']=='file':
            preserved={'kind':'file','document':yaml.safe_load(archive.read(root+'/'+source_path))}
        else:
            preserved={'kind':'bundle','entrypoint':source['entrypoint'],'files':{name:archive.read(root+'/openapi/'+name).decode('utf-8') for name in source['files']}}
        if source_hash(preserved)!=metadata['sourceDigest']:
            raise ReleaseError('SDK ZIP의 보존 명세가 릴리스 원본과 다릅니다.',409)
        archive.writestr(root+'/studio-release.json',json.dumps({
            'releaseId':metadata['releaseId'],'version':metadata['version'],
            'projectRevision':metadata['projectRevision'],'sourceDigest':metadata['sourceDigest'],
            'language':language,'generatorVersion':generator,'sourceKind':source['kind'],'sourcePath':source_path},sort_keys=True,ensure_ascii=False,indent=2))
    value=output.getvalue()
    if len(value)>32*1024*1024:raise ReleaseError('SDK ZIP은 32 MiB 이하여야 합니다.')
    return value


def submit_release_sdk(request, studio):
    def operation(store,reference):
        release_id=request.request.path_params['releaseId']
        language=request.read_body().get('language')
        snapshot,metadata=store.sdk_snapshot(reference,release_id,language)
        manager=request.request.app.state.jobs
        def task(job):
            try:
                # Recheck membership, release availability and duplicate language after queue wait.
                store.sdk_snapshot(reference,release_id,language)
                generator=version('openapi-generator-cli')
                if generator!='7.24.0':raise ReleaseError('고정 SDK 생성기7.24.0이 필요합니다.')
                result=execute_snapshot(snapshot,studio,job.cancel)
                payload=result.pop('_artifact',None);filename=result.pop('_artifact_filename',None)
                if result['status']=='passed':
                    if result.get('generation',{}).get('sourceDigest')!=snapshot['sourceDigest']:
                        raise ReleaseError('SDK 생성 결과의 원본 지문이 릴리스와 다릅니다.',409)
                    payload=_manifest_zip(payload,metadata,language,generator,snapshot)
                    # The durable commit is the cancellation cutoff. cancel() uses this lock.
                    with manager.condition:
                        if job.cancel.is_set():return {'status':'cancelled'}
                        artifact=store.keep_artifact(reference,release_id,language,payload,filename,snapshot['sourceDigest'],generator)
                        job.committed=True
                    result['result']={'format':'zip','releaseId':release_id,'artifact':artifact}
                return result
            except (ReleaseError,PermissionError) as exc:
                return {'status':'error','error':str(exc) if isinstance(exc,ReleaseError) else 'Workspace 실행 권한이 없습니다.'}
            except (OSError,ValueError,KeyError,zipfile.BadZipFile,yaml.YAMLError):
                return {'status':'error','error':'릴리스 SDK를 보존하지 못했습니다.'}
        result=manager.submit(task,owner=store.context,projects=(reference,),initial={'kind':'release_sdk','release':metadata})
        return request.json_response(202,result)
    return _call(request,studio,operation)


def download_release_sdk(request, studio):
    def operation(store,reference):
        if not DOWNLOAD_SLOTS.acquire(blocking=False):raise studio.ApiError('SDK 다운로드 동시 한도를 초과했습니다.',429)
        try:
            payload,filename,digest=store.download_artifact(reference,request.request.path_params['releaseId'],request.request.path_params['language'])
            return ArtifactResponse(payload,media_type='application/zip',headers={
                'Content-Disposition':f'attachment; filename="{filename}"','ETag':'"'+digest+'"',
                'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
        except BaseException:
            DOWNLOAD_SLOTS.release();raise
    return _call(request,studio,operation)


def purge_release_sdk(request, studio):
    return _call(request,studio,lambda store,reference:request.json_response(200,store.purge_artifact(reference,request.request.path_params['releaseId'],request.request.path_params['language'],request.read_body().get('reason'))))
