"""Local-only contract loading; retain recursive references instead of inlining."""
from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import posixpath
from urllib.parse import unquote, urlsplit
import yaml

MAX_BYTES = 5 * 1024 * 1024
MAX_FILES = 200


class ContractError(ValueError):
    pass


def escape(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def pointer(document, reference):
    if not isinstance(reference, str) or not reference.startswith('#/'):
        raise ContractError('Only local JSON Pointer references are supported')
    target = document
    try:
        for part in unquote(reference[2:]).split('/'):
            part = part.replace('~1', '/').replace('~0', '~')
            target = target[int(part)] if isinstance(target, list) else target[part]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ContractError('Unresolved local reference') from None
    return target


def resolve(document, value):
    seen = set()
    while isinstance(value, dict) and '$ref' in value:
        ref = value['$ref']
        if ref in seen:
            raise ContractError('Reference-only cycle is not supported')
        seen.add(ref)
        value = pointer(document, ref)
    return value


def walk(value, path='#', depth=0):
    if depth > 100:
        raise ContractError('Document nesting exceeds 100 levels')
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, path + '/' + escape(key), depth + 1)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + '/' + str(index), depth + 1)


def local_path(parent, reference):
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or parsed.query or '\\' in reference:
        raise ContractError('External references are disabled')
    path = posixpath.normpath(posixpath.join(posixpath.dirname(parent), unquote(parsed.path))) if parsed.path else parent
    if path.startswith('/') or path == '..' or path.startswith('../') or PurePosixPath(path).suffix.lower() not in {'.json', '.yaml', '.yml'}:
        raise ContractError('Reference must stay inside the document directory')
    if parsed.fragment and not parsed.fragment.startswith('/'):
        raise ContractError('Only JSON Pointer fragments are supported')
    return path, parsed.fragment


def bundle_document(bundle):
    entry = bundle.get('entrypoint')
    files = bundle.get('files')
    if not isinstance(entry, str) or not isinstance(files, dict) or entry not in files or not 1 <= len(files) <= MAX_FILES:
        raise ContractError('Invalid OpenAPI bundle')
    if not all(isinstance(name, str) and isinstance(content, str) for name, content in files.items()):
        raise ContractError('Bundle files must contain text')
    if sum(len(text.encode()) for text in files.values()) > MAX_BYTES:
        raise ContractError('OpenAPI document exceeds 5 MB')
    try:
        parsed = {name: yaml.safe_load(text) for name, text in files.items()}
    except yaml.YAMLError:
        raise ContractError('Invalid OpenAPI YAML/JSON') from None
    def rewrite(value, filename, depth=0):
        if depth > 100:
            raise ContractError('Document nesting exceeds 100 levels')
        if isinstance(value, list):
            return [rewrite(item, filename, depth + 1) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: rewrite(item, filename, depth + 1) for key, item in value.items()}
        if '$ref' in result:
            if not isinstance(result['$ref'], str):
                raise ContractError('Reference must be a string')
            target, fragment = local_path(filename, result['$ref'])
            if target not in parsed:
                raise ContractError('Referenced bundle file does not exist')
            result['$ref'] = '#/x-contract-files/' + escape(target) + fragment
        return result
    converted = {name: rewrite(value, name) for name, value in parsed.items()}
    if not isinstance(converted[entry], dict):
        raise ContractError('OpenAPI root must be an object')
    return {**converted[entry], 'x-contract-files': converted}


def load_file(filename):
    filename = Path(filename).resolve()
    root = filename.parent
    pending, files = [filename.name], {}
    while pending:
        name = pending.pop()
        if name in files:
            continue
        target = (root / name).resolve()
        if not target.is_relative_to(root) or target.stat().st_size > MAX_BYTES:
            raise ContractError('Invalid contract file path or size')
        content = target.read_text(encoding='utf-8')
        files[name] = content
        if len(files) > MAX_FILES or sum(len(text.encode()) for text in files.values()) > MAX_BYTES:
            raise ContractError('Contract bundle exceeds size limit')
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError:
            raise ContractError('Invalid OpenAPI YAML/JSON') from None
        for _, value in walk(parsed):
            if isinstance(value, dict) and '$ref' in value:
                if not isinstance(value['$ref'], str):
                    raise ContractError('Reference must be a string')
                ref_path, _ = local_path(name, value['$ref'])
                pending.append(ref_path)
    return bundle_document({'entrypoint': filename.name, 'files': files})


def project_document(project):
    if project.get('docs_bundle') is not None:
        return bundle_document(project['docs_bundle'])
    document = project.get('docs_file', {}).get('document')
    if not isinstance(document, dict):
        raise ContractError('Save an OpenAPI document or bundle in the project first; URL-only revisions have no immutable contract snapshot')
    return deepcopy(document)


def digest(document):
    import hashlib
    try:
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    except (TypeError, ValueError):
        raise ContractError('Contract must contain JSON-compatible values') from None
    return hashlib.sha256(encoded).hexdigest()
