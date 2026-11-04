"""Backward-compatible entrypoint for project pagination."""
from api_test.document_listing import list_document_page


def list_project_page(store, *, page_size='20', search='', sort='reference_asc', cursor='', include_example=True):
    return list_document_page(store, kind='projects', page_size=page_size, search=search,
                              sort=sort, cursor=cursor, include_example=include_example)
