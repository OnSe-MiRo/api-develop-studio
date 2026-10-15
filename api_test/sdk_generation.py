"""Raw-source SDK generation under the existing bounded job and process lifecycle."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import os
import re
from pathlib import Path, PurePosixPath
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import zipfile
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import yaml

from api_test.contracts.documents import ContractError, bundle_document, pointer, walk
from api_test.job_runner import stop_process_tree
from api_test.reports import now

MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_WORK_FILES = 10000
MAX_WORK_BYTES = 128 * 1024 * 1024
MAX_ZIP_BYTES = 32 * 1024 * 1024


class SDKGenerationError(ValueError):
    def __init__(self, message, status='error'):
        super().__init__(message)
        self.status = status


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def snapshot_project(project: dict, reference: str, revision: int, language: str, studio) -> dict:
    if language not in studio.OPENAPI_CLIENT_GENERATORS:
        raise studio.ApiError('지원하지 않는 생성 언어입니다.')
    raw_name = project.get('name') if isinstance(project.get('name'), str) and project['name'].strip() else reference.removesuffix('.json')
    name = (studio.archive_slug(raw_name)[:120] or 'openapi')
    bundle = project.get('docs_bundle')
    file = project.get('docs_file')
    if bundle is not None:
        entry, files = studio.bundle_files(bundle)
        source = {'kind': 'bundle', 'entrypoint': entry, 'files': dict(files)}
    elif isinstance(file, dict) and isinstance(file.get('document'), dict):
        document = deepcopy(file['document'])
        if len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode()) > MAX_SOURCE_BYTES:
            raise studio.ApiError('OpenAPI 원본 크기 한도를 초과했습니다.')
        source = {'kind': 'file', 'document': document}
    elif isinstance(project.get('docs_url'), str) and project['docs_url'].strip():
        # URL is fetched once inside the worker; no network on POST.
        advanced = project.get('advanced')
        use_proxy = advanced.get('use_proxy', True) if isinstance(advanced, dict) else True
        source = {'kind': 'url', 'url': project['docs_url'].strip(), 'no_proxy': use_proxy is False}
    else:
        raise studio.ApiError('저장된 OpenAPI 파일, bundle 또는 URL이 필요합니다.')
    return {'project': reference, 'projectName': name, 'projectRevision': revision,
            'language': language, 'source': source,
            'sourceDigest': None if source['kind'] == 'url' else _digest(source)}


def initial_metadata(snapshot: dict) -> dict:
    return {'project': snapshot['project'], 'language': snapshot['language'],
            'projectRevision': snapshot['projectRevision'], 'sourceKind': snapshot['source']['kind'],
            'sourceDigest': snapshot['sourceDigest'], 'fetchedAt': None,
            'artifactReady': False, 'artifact': None}


def _safe_member_path(relative) -> bool:
    parts = PurePosixPath(str(relative).replace(chr(92), '/')).parts
    return bool(parts) and not str(relative).startswith(('/', chr(92))) and all(
        part not in ('', '.', '..') and ':' not in part and chr(92) not in part for part in parts
    ) and chr(92) not in str(relative)


def _preflight(document, bundle=None):
    try:
        if bundle is not None and any(not _safe_member_path(name) for name in bundle.get('files', {})):
            raise ContractError('Bundle filename is unsafe across platforms')
        linked = bundle_document(bundle) if bundle is not None else document
        for _, value in walk(linked):
            if not isinstance(value, dict):
                continue
            if any(key in value for key in ('$id', '$dynamicRef', '$dynamicAnchor', '$anchor', '$recursiveRef', '$recursiveAnchor')):
                raise ContractError('Reference scope changes are unsupported')
            if '$ref' in value:
                reference = value['$ref']
                if not isinstance(reference, str):
                    raise ContractError('Invalid reference')
                if reference != '#':
                    pointer(linked, reference)
    except (ContractError, KeyError, TypeError, ValueError, RecursionError) as exc:
        raise SDKGenerationError('OpenAPI 로컬 참조를 확인하세요.') from exc


def _fetch_url_once(url: str, no_proxy: bool, studio):
    """One bounded primary request; never follow a redirect to another origin."""
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, headers, newurl):
            return None
    handlers = [NoRedirect()]
    if no_proxy:
        handlers.append(ProxyHandler({}))
    opener = build_opener(*handlers)
    request = Request(url, headers={'Accept': 'application/json, application/yaml, text/yaml'})
    try:
        with opener.open(request, timeout=20) as response:
            content = response.read(MAX_SOURCE_BYTES + 1)
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise SDKGenerationError('OpenAPI URL을 읽거나 검증하지 못했습니다.') from exc
    if len(content) > MAX_SOURCE_BYTES:
        raise SDKGenerationError('OpenAPI URL 원본 크기 한도를 초과했습니다.')
    try:
        text = content.decode('utf-8')
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            document = yaml.safe_load(text)
        studio.openapi_document_operations(document)
    except (UnicodeDecodeError, yaml.YAMLError, ValueError, TypeError) as exc:
        raise SDKGenerationError('OpenAPI URL 원본 형식이 올바르지 않습니다.') from exc
    return document


def _materialize(snapshot, source_root: Path, studio, cancel: threading.Event):
    source = snapshot['source']
    kind = source['kind']
    fetched_at = None
    if cancel.is_set():
        raise SDKGenerationError('SDK 생성이 취소됐습니다.', 'cancelled')
    if kind == 'url':
        document = _fetch_url_once(source['url'], source['no_proxy'], studio)
        source = {'kind': 'file', 'document': document}
        fetched_at = now()
    if kind == 'bundle':
        bundle = {'entrypoint': source['entrypoint'], 'files': source['files']}
        _preflight(None, bundle)
        for name, content in source['files'].items():
            path = source_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        path = source_root / source['entrypoint']
    else:
        document = source['document']
        _preflight(document)
        path = source_root / 'openapi.json'
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    return path, source, fetched_at


def _generator_bundle_copy(snapshot: dict, source_root: Path, generator_root: Path, studio) -> Path:
    """Keep raw ZIP source intact; normalize only JAR's external self-root '#' bug."""
    bundle = snapshot['source']
    generator_root.mkdir()
    for name, original in bundle['files'].items():
        content = original
        if name != bundle['entrypoint']:
            parsed = studio.parse_bundle_file(name, original)
            def normalize(value):
                if isinstance(value, dict):
                    return {key: ('./' + PurePosixPath(name).name if key == '$ref' and child == '#' else normalize(child))
                            for key, child in value.items()}
                if isinstance(value, list):
                    return [normalize(child) for child in value]
                return value
            normalized = normalize(parsed)
            if normalized != parsed:
                content = (json.dumps(normalized, ensure_ascii=False, indent=2) if name.endswith('.json')
                           else studio.yaml_content(normalized))
        target = generator_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    return generator_root / bundle['entrypoint']


def _work_size(root: Path) -> tuple[int, int]:
    files, size = 0, 0
    for path in root.rglob('*'):
        if path.is_symlink():
            raise SDKGenerationError('생성기 symlink 출력은 허용하지 않습니다.')
        if path.is_file():
            try:
                size += path.stat().st_size
            except FileNotFoundError:
                continue  # Generator may replace a temporary file between walk and stat.
            files += 1
            if files > MAX_WORK_FILES or size > MAX_WORK_BYTES:
                raise SDKGenerationError('SDK 생성 작업 크기 한도를 초과했습니다.')
    return files, size


def _process_environment(root: Path) -> dict[str, str]:
    # Exclude source-project variables, user hooks and generator postprocess flags.
    environment = {name: os.environ[name] for name in ('PATH', 'JAVA_HOME', 'LANG', 'LC_ALL', 'SYSTEMROOT')
                   if name in os.environ}
    environment.update(TMPDIR=str(root), TMP=str(root), TEMP=str(root),
                       PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    return environment


def _run_process(command, root: Path, log_name: str, cancel: threading.Event, deadline: float, environment):
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    process = None
    with (root / log_name).open('w+b') as log:
        try:
            if cancel.is_set():
                raise SDKGenerationError('SDK 생성이 취소됐습니다.', 'cancelled')
            if time.monotonic() >= deadline:
                raise SDKGenerationError('SDK 생성 시간이 초과됐습니다.', 'timeout')
            process = subprocess.Popen(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, **options)
            while process.poll() is None:
                if cancel.wait(.05):
                    raise SDKGenerationError('SDK 생성이 취소됐습니다.', 'cancelled')
                if time.monotonic() >= deadline:
                    raise SDKGenerationError('SDK 생성 시간이 초과됐습니다.', 'timeout')
                _work_size(root)
            if process.returncode != 0:
                raise SDKGenerationError('SDK 원본 준비 또는 생성기가 결과를 만들지 못했습니다.', 'failed')
        finally:
            if process is not None:
                stop_process_tree(process)


def _prepare(snapshot_path: Path, source_root: Path, metadata_path: Path):
    """Trusted child: parent supervises this entire parse/fetch/preflight phase."""
    from api_test.services import studio
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    source_root.mkdir(parents=True, exist_ok=True)
    path, source, fetched_at = _materialize(snapshot, source_root, studio, threading.Event())
    generator_path = (_generator_bundle_copy(snapshot, source_root, source_root.parent / 'generator-source', studio)
                      if source['kind'] == 'bundle' else path)
    metadata_path.write_text(json.dumps({
        'sourceKind': source['kind'], 'sourceDigest': _digest(source),
        'fetchedAt': fetched_at, 'sourceFile': path.relative_to(source_root).as_posix(),
        'generatorFile': generator_path.relative_to(source_root.parent).as_posix(),
    }), encoding='utf-8')


def _package(output: Path, source_root: Path, snapshot: dict, source_kind: str,
             cancel: threading.Event, studio, deadline: float):
    root = source_root.parent.resolve()
    if (output.is_symlink() or source_root.is_symlink() or not output.is_dir() or
            not output.resolve().is_relative_to(root) or not source_root.resolve().is_relative_to(root)):
        raise SDKGenerationError('SDK 생성 경로가 작업 디렉터리 밖을 가리킵니다.')
    _work_size(root)  # Reject any symlink before writing preserved source files.
    generated_count, _ = _work_size(output)
    if not generated_count:
        raise SDKGenerationError('SDK 생성기가 파일을 만들지 못했습니다.')
    for generated in output.rglob('*'):
        relative = generated.relative_to(output)
        if not _safe_member_path(relative):
            raise SDKGenerationError('SDK ZIP 멤버 경로가 올바르지 않습니다.')
    if source_kind == 'bundle':
        for reference, content in snapshot['source']['files'].items():
            if cancel.is_set():
                raise SDKGenerationError('SDK 생성이 취소됐습니다.', 'cancelled')
            if time.monotonic() >= deadline:
                raise SDKGenerationError('SDK 생성 시간이 초과됐습니다.', 'timeout')
            destination = output / 'openapi' / reference
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding='utf-8')
    else:
        destination = output / 'openapi.yaml'
        document = json.loads((source_root / 'openapi.json').read_text(encoding='utf-8'))
        destination.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding='utf-8')
    count, _ = _work_size(source_root.parent)
    if not count or not any(path.is_file() for path in output.rglob('*')):
        raise SDKGenerationError('SDK 생성 결과를 찾을 수 없습니다.')
    root_name = f"{studio.archive_slug(snapshot['projectName'])}-{snapshot['language']}-client"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(output.rglob('*')):
            if path.is_symlink():
                raise SDKGenerationError('생성기 symlink 출력은 허용하지 않습니다.')
            if not path.is_file():
                continue
            relative = path.relative_to(output)
            if not _safe_member_path(relative):
                raise SDKGenerationError('SDK ZIP 멤버 경로가 올바르지 않습니다.')
            name = (Path(root_name) / relative).as_posix()
            with path.open('rb') as reader, zip_file.open(name, 'w') as writer:
                while True:
                    if cancel.is_set():
                        raise SDKGenerationError('SDK 생성이 취소됐습니다.', 'cancelled')
                    if time.monotonic() >= deadline:
                        raise SDKGenerationError('SDK 생성 시간이 초과됐습니다.', 'timeout')
                    chunk = reader.read(64 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
                    if archive.tell() > MAX_ZIP_BYTES:
                        raise SDKGenerationError('SDK ZIP 크기 한도를 초과했습니다.')
    value = archive.getvalue()
    if not value or len(value) > MAX_ZIP_BYTES:
        raise SDKGenerationError('SDK ZIP 크기 한도를 초과했습니다.')
    return value, root_name + '.zip'


def execute_snapshot(snapshot: dict, studio, cancel: threading.Event, *, timeout_seconds=None) -> dict:
    timeout = float(timeout_seconds if timeout_seconds is not None else os.environ.get('RUN_TIMEOUT_SECONDS', '300'))
    if not 0 < timeout <= 86400:
        raise SDKGenerationError('SDK 실행 제한이 올바르지 않습니다.')
    deadline = time.monotonic() + timeout
    generation = initial_metadata(snapshot)
    result = {'status': 'error', 'exitCode': None, 'result': None, 'generation': generation}
    try:
        with TemporaryDirectory(prefix='sdk-generation-') as directory:
            root = Path(directory)
            source_root, output = root / 'source', root / 'client'
            environment = _process_environment(root)
            snapshot_path, metadata_path = root / 'snapshot.json', root / 'prepared.json'
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            _run_process([sys.executable, '-m', 'api_test.sdk_generation', '_prepare',
                          str(snapshot_path), str(source_root), str(metadata_path)],
                         root, 'prepare.log', cancel, deadline, environment)
            if not metadata_path.is_file() or metadata_path.stat().st_size > 2048:
                raise SDKGenerationError('SDK 원본 준비 결과를 확인할 수 없습니다.')
            prepared = json.loads(metadata_path.read_text(encoding='utf-8'))
            if prepared.get('sourceKind') not in ('file', 'bundle') or not re.fullmatch(r'[0-9a-f]{64}', str(prepared.get('sourceDigest', ''))):
                raise SDKGenerationError('SDK 원본 준비 결과를 확인할 수 없습니다.')
            source_path = (source_root / prepared.get('sourceFile', '')).resolve()
            if not source_path.is_file() or not source_path.is_relative_to(source_root.resolve()):
                raise SDKGenerationError('SDK 원본 파일을 확인할 수 없습니다.')
            generation['sourceDigest'] = prepared['sourceDigest']
            generation['fetchedAt'] = prepared.get('fetchedAt')
            generator_path = (root / prepared.get('generatorFile', '')).resolve()
            if not generator_path.is_file() or not generator_path.is_relative_to(root.resolve()):
                raise SDKGenerationError('SDK 생성기 원본 파일을 확인할 수 없습니다.')
            command = studio.openapi_generator_command(generator_path,
                        studio.OPENAPI_CLIENT_GENERATORS[snapshot['language']], output)
            java, *rest = command
            command = [java, f'-Duser.home={root.as_posix()}', *rest]
            _run_process(command, root, 'generator.log', cancel, deadline, environment)
            if cancel.is_set():
                raise SDKGenerationError('SDK 생성이 취소됐습니다.', 'cancelled')
            archive, filename = _package(output, source_root, snapshot, prepared['sourceKind'],
                                         cancel, studio, deadline)
            if cancel.is_set():
                raise SDKGenerationError('SDK 생성이 취소됐습니다.', 'cancelled')
            result.update(status='passed', exitCode=0, result={'format': 'zip'},
                          _artifact=archive, _artifact_filename=filename)
    except SDKGenerationError as exc:
        result.update(status=exc.status, error=str(exc))
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile):
        result.update(status='error', error='SDK 생성 작업을 완료하지 못했습니다.')
    # Both process groups and the entire private workdir are gone before publication.
    return result


if __name__ == '__main__' and len(sys.argv) == 5 and sys.argv[1] == '_prepare':
    _prepare(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
