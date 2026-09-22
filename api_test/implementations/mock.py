"""Explicit mock server operation bindings."""

def get_status(request, studio):
    from api_test.services import mock
    return mock.get_status(request, studio)


def start_server(request, studio):
    from api_test.services import mock
    return mock.start_server(request, studio)


def stop_server(request, studio):
    from api_test.services import mock
    return mock.stop_server(request, studio)


def reset_server(request, studio):
    from api_test.services import mock
    return mock.reset_server(request, studio)


def update_config(request, studio):
    from api_test.services import mock
    return mock.update_config(request, studio)
