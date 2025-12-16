import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.meta import ManualRequiredUploadError, RetryableUploadError, upload_meta_target
from uploader.models import UploadJob, UploadTarget


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def api_post(self, path, **kwargs):
        self.calls.append(("post", path, kwargs))
        if isinstance(self._responses[0], Exception):
            raise self._responses.pop(0)
        return self._responses.pop(0)

    def api_get(self, path, **kwargs):
        self.calls.append(("get", path, kwargs))
        return self._responses.pop(0)


def _client_factory_with_responses(responses):
    def _factory(token):
        return _FakeClient(list(responses))

    return _factory


def _job_and_target(tmp_path: Path):
    video = tmp_path / "video.mp4"
    video.write_text("video")
    job = UploadJob(file_path=video, title="Title", description="Desc", targets=[])
    target = UploadTarget(platform="instagram", account_id="ig_main")
    job.targets.append(target)
    return job, target


def test_instagram_missing_token_triggers_manual_required(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"meta": {"ig_main": {"platform": "instagram", "ig_user_id": "123", "access_token_env": "MISSING"}}}
    monkeypatch.delenv("MISSING", raising=False)
    with pytest.raises(ManualRequiredUploadError):
        upload_meta_target(job, target, accounts_config=accounts)


def test_instagram_success_flow(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"meta": {"ig_main": {"platform": "instagram", "ig_user_id": "123", "access_token_env": "TOKEN_ENV"}}}
    monkeypatch.setenv("TOKEN_ENV", "secret")
    responses = [
        {"id": "creation123"},
        {"status_code": "FINISHED"},
        {"id": "media456"},
    ]
    monkeypatch.setattr("time.sleep", lambda _: None)
    result_id = upload_meta_target(job, target, accounts_config=accounts, client_factory=_client_factory_with_responses(responses))
    assert result_id == "media456"


def test_instagram_permission_error_manual_required(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"meta": {"ig_main": {"platform": "instagram", "ig_user_id": "123", "access_token_env": "TOKEN_ENV"}}}
    monkeypatch.setenv("TOKEN_ENV", "secret")
    responses = [ManualRequiredUploadError("permissions error")]
    with pytest.raises(ManualRequiredUploadError):
        upload_meta_target(job, target, accounts_config=accounts, client_factory=_client_factory_with_responses(responses))


def test_instagram_retryable_processing_timeout(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"meta": {"ig_main": {"platform": "instagram", "ig_user_id": "123", "access_token_env": "TOKEN_ENV"}}}
    monkeypatch.setenv("TOKEN_ENV", "secret")
    responses = [
        {"id": "creation123"},
        {"status_code": "PROCESSING"},
    ]

    class SlowClient(_FakeClient):
        def api_get(self, path, **kwargs):
            self.calls.append(("get", path, kwargs))
            raise RetryableUploadError("timeout", status_code=504)

    def factory(token):
        return SlowClient(list(responses))

    with pytest.raises(RetryableUploadError):
        upload_meta_target(job, target, accounts_config=accounts, client_factory=factory)

