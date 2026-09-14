"""Legacy execution dispatch adapter."""
from api_test.services import execution


def handle_post(request, parts, studio):
    if parts == ['api', 'request']:
        return execution.send_request(request, studio)
    if parts == ['api', 'run']:
        return execution.run_tests(request, studio)
    return False
