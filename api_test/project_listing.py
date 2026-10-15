"""Bounded, workspace-scoped project pages with bidirectional keyset cursors."""
import base64
import binascii
import hashlib
import json
from contextlib import closing


SORTS = {'reference_asc', 'reference_desc', 'created_desc'}


def list_project_page(store, *, page_size='20', search='', sort='reference_asc', cursor='', include_example=True):
    if not isinstance(page_size, str) or not page_size.isascii() or not page_size.isdecimal() or not 1 <= int(page_size) <= 100:
        raise ValueError('페이지 크기는 1~100이어야 합니다.')
    limit = int(page_size)
    search = search.strip()
    if len(search) > 100 or sort not in SORTS:
        raise ValueError('검색어 또는 정렬 조건이 올바르지 않습니다.')
    scope = hashlib.sha256(json.dumps([store.context.workspace_id, search, sort, limit, include_example], ensure_ascii=False).encode()).hexdigest()
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
        except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error):
            raise ValueError('커서가 올바르지 않거나 조회 조건이 변경되었습니다.') from None
    with closing(store.connect()) as db, db:
        postgres = getattr(db, 'dialect', '') == 'postgresql'
        ref = 'd.reference COLLATE "C"' if postgres else 'd.reference COLLATE BINARY'
        name = "(r.content::jsonb ->> 'name')" if postgres else "json_extract(r.content, '$.name')"
        where = "d.workspace_id = ? AND d.kind = 'projects' AND d.deleted_at IS NULL"
        params = [store.context.workspace_id]
        if not include_example:
            where += ' AND d.reference <> ?'
            params.append('example-api.json')
        if search:
            pattern = '%' + search.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
            where += f" AND (LOWER(d.reference) LIKE LOWER(?) ESCAPE '!' OR LOWER(COALESCE({name}, '')) LIKE LOWER(?) ESCAPE '!')"
            params.extend([pattern, pattern])
        ascending = sort == 'reference_asc'
        if direction == 'previous':
            ascending = not ascending
        order = 'ASC' if ascending else 'DESC'
        operator = '>' if ascending else '<'
        if anchor:
            if sort == 'created_desc':
                where += f' AND (d.created_at {operator} ? OR (d.created_at = ? AND {ref} {operator} ?))'
                params.extend([anchor[0], anchor[0], anchor[1]])
            else:
                where += f' AND {ref} {operator} ?'
                params.append(anchor[1])
        ordering = f'd.created_at {order}, {ref} {order}' if sort == 'created_desc' else f'{ref} {order}'
        rows = db.execute(f'''SELECT d.reference, d.created_at, r.content FROM documents d
            JOIN document_revisions r ON r.document_id = d.id AND r.revision = d.current_revision
            WHERE {where} ORDER BY {ordering} LIMIT ?''', [*params, limit + 1]).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    if direction == 'previous':
        rows.reverse()

    def token(row, target):
        value = {'scope': scope, 'direction': target, 'anchor': [row['created_at'], row['reference']]}
        return base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=False).encode()).decode()

    details = {}
    for row in rows:
        document = json.loads(row['content'])
        details[row['reference']] = {key: document.get(key, '') if isinstance(document.get(key, ''), str) else '' for key in ('name', 'base_url')}
    return {'items': [row['reference'] for row in rows], 'details': details,
            'nextCursor': token(rows[-1], 'next') if rows and (more if direction == 'next' else bool(cursor)) else None,
            'previousCursor': token(rows[0], 'previous') if rows and (bool(cursor) if direction == 'next' else more) else None}
