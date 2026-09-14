"""Legacy dispatch adapter. New HTTP routes are generated from Studio OpenAPI."""
from api_test.services import documents


def _reference(request, parts):
    if len(parts) >= 3:
        request.request.path_params['reference'] = parts[2]


def handle_get(request, parts, studio):
    if len(parts) < 2 or parts[0] != 'api' or parts[1] not in {'projects', 'cases', 'pipelines'}:
        return False
    _reference(request, parts)
    if len(parts) == 2:
        return documents.list_documents(request, studio, parts[1])
    if len(parts) == 3:
        return documents.get_document(request, studio, parts[1])
    if len(parts) == 4 and parts[3] == 'revisions':
        return documents.list_revisions(request, studio, parts[1])
    return False


def handle_put(request, parts, studio):
    if len(parts) != 3 or parts[0] != 'api' or parts[1] not in {'projects', 'cases', 'pipelines'}:
        return False
    _reference(request, parts)
    return documents.save_document(request, studio, parts[1])


def handle_delete(request, parts, studio):
    if len(parts) != 3 or parts[0] != 'api' or parts[1] not in {'projects', 'cases', 'pipelines'}:
        return False
    _reference(request, parts)
    return documents.delete_document(request, studio, parts[1])
