"""Bounded document pages; callers select a supported document kind."""
import base64
import binascii
import hashlib
import json
from contextlib import closing

from api_test.case_projection import case_url


PROJECT_SORTS = {'reference_asc', 'reference_desc', 'created_desc'}
CASE_SORTS = {'name_asc', 'name_desc', 'created_desc'}


def list_document_page(store, *, kind, page_size='20', search='', sort='reference_asc', cursor='', include_example=True, project=None, tag=''):
    if kind not in ('projects', 'cases', 'pipelines'):
        raise ValueError('지원하지 않는 문서 종류입니다.')
    tag = tag.strip()
    if kind != 'projects' and (not isinstance(project, str) or not project or len(project) > 1024 or len(tag) > 128 or '/' in tag or '\\' in tag):
        raise ValueError('프로젝트 또는 태그 조건이 올바르지 않습니다.')
    if not isinstance(page_size, str) or not page_size.isascii() or not page_size.isdecimal() or not 1 <= int(page_size) <= 100:
        raise ValueError('페이지 크기는 1~100이어야 합니다.')
    limit = int(page_size)
    search = search.strip()
    if len(search) > 100 or sort not in (CASE_SORTS if kind == 'cases' else PROJECT_SORTS):
        raise ValueError('검색어 또는 정렬 조건이 올바르지 않습니다.')
    scope_values = [store.context.workspace_id, search, sort, limit, include_example]
    if kind != 'projects':
        scope_values.extend([kind, project, tag])
    scope = hashlib.sha256(json.dumps(scope_values, ensure_ascii=False).encode()).hexdigest()
    anchor = None
    direction = 'next'
    if cursor:
        try:
            if len(cursor) > 4096:
                raise ValueError()
            value = json.loads(base64.b64decode(cursor.encode('ascii'), altchars=b'-_', validate=True))
            if not isinstance(value, dict) or value.get('scope') != scope or value.get('direction') not in ('next', 'previous'):
                raise ValueError()
            anchor = value['anchor']
            if not isinstance(anchor, list) or len(anchor) != 2 or any(not isinstance(x, str) or not x or len(x) > 1024 for x in anchor):
                raise ValueError()
            direction = value['direction']
        except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error, RecursionError):
            raise ValueError('커서가 올바르지 않거나 조회 조건이 변경되었습니다.') from None
    with closing(store.connect()) as db, db:
        postgres = getattr(db, 'dialect', '') == 'postgresql'
        ref = 'd.reference COLLATE "C"' if postgres else 'd.reference COLLATE BINARY'
        name = "(r.content::jsonb ->> 'name')" if postgres else "json_extract(r.content, '$.name')"
        where = 'd.workspace_id = ? AND d.kind = ? AND d.deleted_at IS NULL'
        params = [store.context.workspace_id, kind]
        if kind != 'projects':
            where += ' AND d.project_reference = ?'
            params.append(project)
            if kind == 'cases' and tag:
                tag_key = "split_part(d.reference, '/', 1)" if postgres else "substr(d.reference, 1, instr(d.reference, '/') - 1)"
                where += f' AND {tag_key} = ?'
                params.append(tag)
        if kind == 'projects' and not include_example:
            where += ' AND d.reference <> ?'
            params.append('example-api.json')
        if search:
            pattern = '%' + search.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
            where += f" AND (LOWER(d.reference) LIKE LOWER(?) ESCAPE '!' OR LOWER(COALESCE({name}, '')) LIKE LOWER(?) ESCAPE '!')"
            params.extend([pattern, pattern])
        if kind == 'cases':
            # case/{tag}/{api_name}/{case_file}.json is the persisted reference contract.
            remainder = "substr(d.reference, instr(d.reference, '/') + 1)"
            filename = "split_part(d.reference, '/', 3)" if postgres else f"substr({remainder}, instr({remainder}, '/') + 1)"
            name_key = f'{filename} COLLATE "C"' if postgres else f'{filename} COLLATE BINARY'
        else:
            name_key = ref
        key = 'd.created_at' if sort == 'created_desc' else name_key
        ascending = sort in ('reference_asc', 'name_asc')
        if direction == 'previous':
            ascending = not ascending
        order = 'ASC' if ascending else 'DESC'
        operator = '>' if ascending else '<'
        if anchor:
            if kind == 'cases' or sort == 'created_desc':
                where += f' AND ({key} {operator} ? OR ({key} = ? AND {ref} {operator} ?))'
                params.extend([anchor[0], anchor[0], anchor[1]])
            else:
                where += f' AND {ref} {operator} ?'
                params.append(anchor[1])
        rows = db.execute(f'''SELECT d.reference, d.created_at, {key} AS sort_key, r.content FROM documents d
            JOIN document_revisions r ON r.document_id = d.id AND r.revision = d.current_revision
            WHERE {where} ORDER BY {key} {order}, {ref} {order} LIMIT ?''', [*params, limit + 1]).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    if direction == 'previous':
        rows.reverse()

    def token(row, target):
        value = {'scope': scope, 'direction': target, 'anchor': [row['sort_key'] if kind == 'cases' else row['created_at'], row['reference']]}
        return base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=False).encode()).decode()

    details = {}
    for row in rows:
        document = json.loads(row['content'])
        if kind == 'projects':
            details[row['reference']] = {key: document.get(key, '') if isinstance(document.get(key, ''), str) else '' for key in ('name', 'base_url')}
        elif kind == 'cases':
            details[row['reference']] = {'url': case_url(document)}
    return {'items': [row['reference'] for row in rows], 'details': details,
            'nextCursor': token(rows[-1], 'next') if rows and (more if direction == 'next' else bool(cursor)) else None,
            'previousCursor': token(rows[0], 'previous') if rows and (bool(cursor) if direction == 'next' else more) else None}
