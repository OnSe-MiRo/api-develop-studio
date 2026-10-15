"""Generated SDK DTOs must resolve constrained and timestamp field types."""
import json
import unittest

from pydantic import ValidationError
from api_test.generated.models.run_job import RunJob
from api_test.generated.models.sdk_generation_request import SdkGenerationRequest


class SdkGeneratedModelTests(unittest.TestCase):
    def metadata(self):
        return dict(project='example.json', language='python', projectRevision=2,
                    sourceKind='url', sourceDigest=None, fetchedAt=None,
                    artifactReady=False, artifact=None)

    def test_queued_sdk_job_preserves_explicit_unknown_source_and_artifact(self):
        job = RunJob.from_dict(dict(runId='sdk-run', status='queued', createdAt='2026-10-04T00:00:00Z',
                                    kind='sdk_generation', generation=self.metadata()))
        result = json.loads(job.model_dump_json(by_alias=True, exclude_unset=True))
        self.assertEqual(result['generation'], self.metadata())

    def test_completed_sdk_artifact_timestamp_and_revision_constraints(self):
        generation = self.metadata()
        generation.update(sourceDigest='a' * 64, fetchedAt='2026-10-04T00:00:00Z', artifactReady=True,
                          artifact={'sizeBytes': 100, 'sha256': 'b' * 64,
                                    'expiresAt': '2026-10-04T00:10:00Z'})
        job = RunJob.from_dict(dict(runId='sdk-run', status='passed', createdAt='2026-10-04T00:00:00Z',
                                   kind='sdk_generation', generation=generation))
        self.assertEqual(job.generation.artifact.size_bytes, 100)
        self.assertIsNotNone(job.generation.artifact.expires_at.tzinfo)
        self.assertEqual(json.loads(job.model_dump_json(by_alias=True))['generation']['artifact']['sha256'], 'b' * 64)
        for revision in (0, True):
            with self.assertRaises(ValidationError):
                SdkGenerationRequest(project='example.json', language='python', projectRevision=revision)
