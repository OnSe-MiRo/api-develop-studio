"""Bindings from generated SDK endpoints to the shared generation service."""
from api_test.services import sdk_generation


def submit_generation(request, studio):
    return sdk_generation.submit_generation(request, studio)


def download_artifact(request, studio):
    return sdk_generation.download_artifact(request, studio, request.request.path_params["runId"])
