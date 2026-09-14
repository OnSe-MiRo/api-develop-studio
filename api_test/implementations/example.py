"""Bundled Example endpoints retain their public fixture policy."""
def handle_example(request, studio):
    return request.example_response()
