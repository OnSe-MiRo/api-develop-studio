"""Legacy OpenAPI dispatch adapter."""
from api_test.services import openapi


def handle_post(request, parts, studio):
    if parts == ['api', 'docs']:
        return openapi.inspect_document(request, studio)
    if parts == ['api', 'generate']:
        return openapi.generate_client(request, studio)
    if len(parts) == 5 and parts[:2] == ['api', 'projects'] and parts[3:] == ['openapi', 'operations']:
        request.request.path_params['reference'] = parts[2]
        return openapi.author_operation(request, studio)
    return False
