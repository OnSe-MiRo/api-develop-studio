"""Legacy dashboard dispatch adapter."""
from api_test.services.dashboard import get_dashboard


def handle_get(request, parts, studio):
    return get_dashboard(request, studio) if parts == ['api', 'dashboard'] else False
