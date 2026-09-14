"""Bounded attachment upload implementation."""
def upload_attachment(request, studio):
    path = studio.safe_attachment_file(studio.CASE_ROOT, request.request.path_params['reference'])
    content = request.read_upload()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return request.json_response(200, {'path': path.relative_to(studio.CASE_ROOT).as_posix()})
