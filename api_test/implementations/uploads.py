"""Bounded attachment upload implementation."""
def upload_attachment(request, studio):
    path = studio.safe_attachment_file(studio.document_root("cases"), request.request.path_params['reference'])
    content = request.read_upload()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return request.json_response(200, {'path': path.relative_to(studio.document_root("cases")).as_posix()})
